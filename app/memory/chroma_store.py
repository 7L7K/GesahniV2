"""Chroma-backed vector store implementation."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple

from app import metrics
from app.telemetry import hash_user_id

try:  # pragma: no cover - optional dependency
    import chromadb
except ImportError:  # pragma: no cover - optional dependency
    chromadb = None

from .env_utils import _clean_meta, _env_flag, _get_sim_threshold, _normalize
from .memory_store import VectorStore


logger = logging.getLogger(__name__)


class _LengthEmbedder:
    _type = "LengthEmbedder"

    def __call__(self, input: List[str]) -> List[List[float]]:
        import numpy as np

        return [
            np.asarray([float(len(_normalize(t)[1]))], dtype=np.float32) for t in input
        ]

    def name(self) -> str:  # pragma: no cover - simple helper
        return "length-embedder"


class _ChromaCacheWrapper:
    """Adapter exposing a minimal collection-like API for Chroma."""

    def __init__(self, collection) -> None:  # type: ignore[no-untyped-def]
        self._col = collection

    def get_items(
        self, ids: List[str] | None = None, include: List[str] | None = None
    ) -> Dict[str, List]:
        """Delegate to the underlying collection's ``get`` method."""

        return self._col.get(ids=ids, include=include)

    def keys(self) -> List[str]:
        """Return all document identifiers from the collection."""

        return self._col.get(include=[]).get("ids", [])

    def __getattr__(self, name):  # pragma: no cover - simple delegation
        return getattr(self._col, name)


class ChromaVectorStore(VectorStore):
    def __init__(self) -> None:
        self._dist_cutoff = 1.0 - _get_sim_threshold()

        use_cloud = os.getenv("VECTOR_STORE", "local").lower() == "cloud"

        if use_cloud:
            from chromadb import CloudClient

            client = CloudClient(
                api_key=os.getenv("CHROMA_API_KEY", ""),
                tenant=os.getenv("CHROMA_TENANT_ID", ""),
                database=os.getenv("CHROMA_DATABASE_NAME", ""),
            )
        else:
            path = os.getenv("CHROMA_PATH", ".chroma_data")
            os.makedirs(path, exist_ok=True)
            from chromadb import PersistentClient

            client = PersistentClient(path=path)

        self._client = client
        self._embedder = _LengthEmbedder()
        base_cache = self._client.get_or_create_collection(
            "qa_cache", embedding_function=self._embedder
        )
        self._cache = _ChromaCacheWrapper(base_cache)
        self._user_memories = self._client.get_or_create_collection(
            "user_memories", embedding_function=self._embedder
        )

    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        self._user_memories.upsert(
            ids=[mem_id],
            documents=[memory],
            metadatas=[{"user_id": user_id, "ts": time.time()}],
        )
        hashed = hash_user_id(user_id)
        metrics.USER_MEMORY_ADDS.labels("chroma", hashed).inc()
        logger.debug("Added user memory %s for %s", mem_id, hashed)
        return mem_id

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
        self._dist_cutoff = 1.0 - _get_sim_threshold()
        res = self._user_memories.query(
            query_texts=[prompt],
            where={"user_id": user_id},
            n_results=k,
            include=["documents", "distances", "metadatas"],
        )
        docs, dists, metas = (
            res.get("documents", "[[]]")[0],
            res.get("distances", "[[]]")[0],
            res.get("metadatas", "[[]]")[0],
        )
        items: List[Tuple[float, float, str]] = []
        for doc, dist, meta in zip(docs, dists, metas):
            if doc and float(dist) <= self._dist_cutoff:
                items.append((float(dist), -float(meta.get("ts", 0)), doc))
        items.sort()
        return [doc for _, _, doc in items[:k]]

    @property
    def qa_cache(self):  # type: ignore[override]
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        if _env_flag("DISABLE_QA_CACHE"):
            return
        _, norm = _normalize(prompt)
        raw_meta = {"answer": answer, "timestamp": time.time(), "feedback": None}
        cleaned = _clean_meta(raw_meta)
        self._cache.upsert(
            ids=[cache_id],
            documents=[norm],
            metadatas=[cleaned],
        )

    def lookup_cached_answer(
        self, prompt: str, ttl_seconds: int = 86400
    ) -> Optional[str]:
        self._dist_cutoff = 1.0 - _get_sim_threshold()
        hash_, norm = _normalize(prompt)
        if _env_flag("DISABLE_QA_CACHE"):
            logger.debug("QA cache disabled; miss for %s", hash_)
            return None
        res = self._cache.query(
            query_texts=[norm], n_results=1, include=["metadatas", "documents"]
        )
        ids = res.get("ids", [[]])[0]
        if not ids:
            logger.debug("Cache miss for %s", hash_)
            return None
        doc = res.get("documents", [[]])[0][0] or ""
        meta = res.get("metadatas", [[]])[0][0] or {}
        dist = abs(len(doc) - len(norm)) / max(len(doc), len(norm), 1)
        if dist >= self._dist_cutoff:
            logger.debug("Cache miss for %s (dist=%.4f > cutoff)", hash_, dist)
            return None
        ts = float(meta.get("timestamp", 0))
        if ttl_seconds and time.time() - ts > ttl_seconds:
            logger.debug("Cache expired for %s", hash_)
            self._cache.delete(ids=[ids[0]])
            return None
        if meta.get("feedback") == "down":
            logger.debug("Cache invalidated by feedback for %s", hash_)
            self._cache.delete(ids=[ids[0]])
            return None
        logger.debug("Cache hit for %s (dist=%.4f)", hash_, dist)
        return meta.get("answer")

    def record_feedback(self, prompt: str, feedback: str) -> None:
        if _env_flag("DISABLE_QA_CACHE"):
            return
        cid = _normalize(prompt)[0]
        self._cache.update(ids=[cid], metadatas=[{"feedback": feedback}])
        if feedback == "down":
            logger.debug("Cache invalidated by feedback for %s", cid)
            self._cache.delete(ids=[cid])

    def close(self) -> None:  # pragma: no cover - thin wrapper
        client = getattr(self, "_client", None)
        if client is None:
            return
        try:
            close = getattr(client, "close", None)
            if callable(close):
                close()
            else:
                reset = getattr(client, "reset", None)
                if callable(reset):
                    reset()
        except Exception:  # pragma: no cover - best effort
            pass
        self._client = None


__all__ = ["ChromaVectorStore"]
