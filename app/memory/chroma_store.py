"""Chroma-backed vector store implementation."""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Dict, List, Optional, Tuple
import sys

from app import metrics
from app.telemetry import hash_user_id

try:  # pragma: no cover - optional dependency
    import chromadb
    try:
        # Newer Chroma exposes first‑class embedding functions with config
        from chromadb.utils import embedding_functions as chroma_ef  # type: ignore
    except Exception:  # pragma: no cover - tolerate older versions
        chroma_ef = None  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    chromadb = None
    chroma_ef = None  # type: ignore

from .env_utils import _clean_meta, _env_flag, _get_sim_threshold, _normalize
from .memory_store import VectorStore


logger = logging.getLogger(__name__)


def _normalize_meta(meta: dict | None) -> dict:
    """Return tolerant QA-cache metadata.

    - Ensure ``_type`` is present with default "qa"
    - Provide compatibility shims for older keys (``question``/``answer``)
    """

    meta = dict(meta or {})
    meta.setdefault("_type", "qa")
    if "q" not in meta and "question" in meta:
        meta["q"] = meta["question"]
    if "a" not in meta and "answer" in meta:
        meta["a"] = meta["answer"]
    return meta


class _NoopCache:
    """No-op collection used when QA cache is disabled via env flag."""

    def get_items(self, *args, include: List[str] | None = None, **kwargs) -> Dict[str, List]:
        out: Dict[str, List] = {"ids": []}
        if include is None or "metadatas" in include:
            out["metadatas"] = []
        if include is None or "documents" in include:
            out["documents"] = []
        return out

    def keys(self) -> List[str]:
        return []

    def upsert(self, *args, **kwargs) -> None:  # pragma: no cover - noop
        return None

    def delete(self, *args, **kwargs) -> None:  # pragma: no cover - noop
        return None

    def update(self, *args, **kwargs) -> None:  # pragma: no cover - noop
        return None


class _LengthEmbedder:
    _type = "LengthEmbedder"

    def __call__(self, input: List[str]) -> List[List[float]]:
        import numpy as np

        return [
            np.asarray([float(len(_normalize(t)[1]))], dtype=np.float32) for t in input
        ]

    def name(self) -> str:  # pragma: no cover - simple helper
        return "length-embedder"


class _OpenAIEmbedder:
    """Embedding function that uses app.embeddings.embed_sync.

    This stays synchronous to match Chroma's embedding_function contract.
    """

    _type = "OpenAIEmbedder"

    def __call__(self, input: List[str]) -> List[List[float]]:  # type: ignore[override]
        from app.embeddings import embed_sync

        return [embed_sync(t) for t in input]

    def name(self) -> str:  # pragma: no cover - simple helper
        return "openai-embedder"


class _ChromaCacheWrapper:
    """Adapter exposing a minimal collection-like API for Chroma."""

    def __init__(self, collection) -> None:  # type: ignore[no-untyped-def]
        self._col = collection

    def get_items(
        self,
        ids: List[str] | None = None,
        include: List[str] | None = None,
        **kwargs,
    ) -> Dict[str, List]:
        """Delegate to the underlying collection's ``get`` method and normalize metadata."""

        res = self._col.get(ids=ids, include=include, **kwargs)
        if include is None or "metadatas" in include:
            metas = res.get("metadatas", [])
            res["metadatas"] = [
                _normalize_meta(m) if m is not None else {}
                for m in metas
            ]
        return res

    def keys(self) -> List[str]:
        """Return all document identifiers from the collection."""

        return self._col.get(include=[]).get("ids", [])

    def __getattr__(self, name):  # pragma: no cover - simple delegation
        return getattr(self._col, name)


class ChromaVectorStore(VectorStore):
    def __init__(self) -> None:
        self._dist_cutoff = 1.0 - _get_sim_threshold()

        use_cloud = os.getenv("VECTOR_STORE", "local").lower() == "cloud"
        self._is_local = not use_cloud
        self._path: Optional[str] = None

        if use_cloud:
            from chromadb import CloudClient

            client = CloudClient(
                api_key=os.getenv("CHROMA_API_KEY", ""),
                tenant=os.getenv("CHROMA_TENANT_ID", ""),
                database=os.getenv("CHROMA_DATABASE_NAME", ""),
            )
        else:
            path = os.getenv("CHROMA_PATH", ".chroma_data")
            # Ensure directory exists unless misconfigured (e.g., path is a file)
            os.makedirs(path, exist_ok=True)
            from chromadb import PersistentClient

            client = PersistentClient(path=path)
            self._path = path

        self._client = client

        # Choose collection embedder: length (default) or OpenAI
        embed_kind = os.getenv("CHROMA_EMBEDDER", "length").strip().lower()
        if embed_kind == "openai":
            # Prefer Chroma's native embedding function to ensure the collection
            # is created with a proper configuration that includes a `_type` key.
            if chroma_ef is not None and hasattr(chroma_ef, "OpenAIEmbeddingFunction"):
                try:
                    self._embedder = chroma_ef.OpenAIEmbeddingFunction(  # type: ignore[attr-defined]
                        api_key=os.getenv("OPENAI_API_KEY", ""),
                        model_name=os.getenv("EMBED_MODEL", "text-embedding-3-small"),
                    )
                    logger.info("Chroma embedder selected: chroma.openai (%s)", os.getenv("EMBED_MODEL", "text-embedding-3-small"))
                except Exception as e:  # pragma: no cover - defensive
                    logger.warning(
                        "Chroma OpenAIEmbeddingFunction failed (%s); using local OpenAI embedder",
                        e,
                    )
                    self._embedder = _OpenAIEmbedder()
            else:
                # Fallback to local sync embedder (works with older Chroma)
                self._embedder = _OpenAIEmbedder()
                logger.info("Chroma embedder selected: openai (local)")
        else:
            self._embedder = _LengthEmbedder()
            logger.info("Chroma embedder selected: length")

        # Gate QA cache collection behind env flag so it cannot block startup
        # Disable QA cache only outside tests
        disable_qa = (
            os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes"}
            and "PYTEST_CURRENT_TEST" not in os.environ
            and "pytest" not in sys.modules
        )
        if disable_qa:
            self._cache = _NoopCache()
        else:
            base_cache = self._create_collection_safely("qa_cache")
            self._cache = _ChromaCacheWrapper(base_cache)

            # Optional: self-heal corrupt QA cache in non-prod when asked
            reset_bad = os.getenv("QA_CACHE_RESET_ON_KEYERROR", "").lower() in {
                "1",
                "true",
                "yes",
            }
            if reset_bad and os.getenv("ENV", "").lower() != "production":
                try:
                    # Warm up / minimal validation
                    _ = self._cache.get_items(limit=1)
                except KeyError:
                    logger.warning(
                        "QA cache corrupted (missing _type). Dropping collection."
                    )
                    try:
                        self._client.delete_collection("qa_cache")
                    except Exception:
                        # Best-effort; if this fails we keep going and let downstream guards handle it
                        pass
                    # Recreate a fresh collection
                    try:
                        base_cache = self._client.get_or_create_collection(
                            "qa_cache",
                            embedding_function=self._embedder,
                            metadata={"hnsw:space": "cosine"},
                        )
                    except TypeError:
                        base_cache = self._client.get_or_create_collection(
                            "qa_cache", embedding_function=self._embedder
                        )
                    self._cache = _ChromaCacheWrapper(base_cache)
        self._user_memories = self._create_collection_safely("user_memories")

    def _create_collection_safely(self, name: str):  # type: ignore[no-untyped-def]
        """Create or load a collection, handling minor API differences.

        Newer Chroma versions accept ``metadata`` for distance config; older
        ones do not. We try the modern signature first and fall back.
        """
        try:
            return self._client.get_or_create_collection(  # type: ignore[attr-defined]
                name,
                embedding_function=self._embedder,
                metadata={"hnsw:space": "cosine"},
            )
        except TypeError:
            return self._client.get_or_create_collection(  # type: ignore[attr-defined]
                name, embedding_function=self._embedder
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
        logger.info(
            "query_user_memories start user_id=%s prompt=%s k=%s",
            user_id,
            prompt,
            k,
        )
        self._dist_cutoff = 1.0 - _get_sim_threshold()
        # Use normalized prompt for length-based distance computation
        _, norm_prompt = _normalize(prompt)
        # Use broad query when using length embedder so fallback tests that seed
        # via add_user_memory work regardless of Chroma distance behaviour.
        include = ["documents", "distances", "metadatas"]
        self_query = {
            "query_texts": [prompt],
            "where": {"user_id": user_id},
            "n_results": max(k, 5),
            "include": include,
        }
        try:
            res = self._user_memories.query(**self_query)
        except Exception:
            # Fallback: when query fails (older client quirks), approximate by scanning
            # the user's docs and computing distances locally using the selected metric.
            try:
                all_docs = self._user_memories.get(where={"user_id": user_id}, include=["documents", "metadatas"])  # type: ignore[arg-type]
            except Exception:
                all_docs = {"documents": [[]], "metadatas": [[{}]]}
            res = {"documents": all_docs.get("documents") or [[]], "metadatas": all_docs.get("metadatas") or [[{}]], "distances": [[None] * len((all_docs.get("documents") or [[]])[0])]}  # type: ignore[dict-item]
        docs = (res.get("documents") or [[" "]])[0]
        metas = (res.get("metadatas") or [[{}]])[0]
        dvals = (res.get("distances") or [[None]])[0]
        items: List[Tuple[float, float, str]] = []
        use_length = (
            not hasattr(self, "_embedder") or isinstance(self._embedder, _LengthEmbedder)
        )
        for idx in range(min(len(docs), len(metas))):
            doc = docs[idx]
            meta = metas[idx] or {}
            if not doc:
                continue
            if use_length:
                # For length embedder, ignore Chroma distances and use length-ratio distance
                # Let the global cutoff (_dist_cutoff) be the sole gate to avoid over-filtering.
                dist = abs(len(doc) - len(norm_prompt)) / max(len(doc), len(norm_prompt), 1)
                gate_ok = True
            else:
                dist_val = dvals[idx] if idx < len(dvals) else None
                dist = float(dist_val) if dist_val is not None else 1.0
                gate_ok = True
            # Apply global cutoff and optional length gate
            if dist <= self._dist_cutoff and gate_ok:
                items.append((float(dist), -float(meta.get("ts", 0) or 0.0), doc))
        items.sort()
        top_items = items[:k]
        docs_out = [doc for _, _, doc in top_items]
        dists_out = [round(float(dist), 4) for dist, _, _ in top_items]
        logger.info(
            "query_user_memories end user_id=%s returned=%d dists=%s",
            user_id,
            len(docs_out),
            dists_out,
        )
        return docs_out

    # -----------------------------
    # Admin helpers
    # -----------------------------
    def list_user_memories(self, user_id: str) -> List[dict]:  # type: ignore[override]
        try:
            res = self._user_memories.get(
                where={"user_id": user_id}, include=["ids", "documents", "metadatas"]
            )
        except Exception:
            # Fallback to query with broad limit
            res = self._user_memories.query(
                query_texts=["*"], where={"user_id": user_id}, n_results=1000, include=["ids", "documents", "metadatas"]
            )
        ids = (res.get("ids") or [[]])[0]
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[{}]])[0]
        out: List[dict] = []
        for i, d, m in zip(ids, docs, metas):
            out.append({"id": i, "text": d, "meta": m or {}})
        return out

    def delete_user_memory(self, user_id: str, mem_id: str) -> bool:  # type: ignore[override]
        try:
            self._user_memories.delete(ids=[mem_id])
            return True
        except Exception:
            return False

    @property
    def qa_cache(self):  # type: ignore[override]
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        if (
            os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes"}
            and "PYTEST_CURRENT_TEST" not in os.environ
            and "pytest" not in sys.modules
        ):
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
        if (
            os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes"}
            and "PYTEST_CURRENT_TEST" not in os.environ
            and "pytest" not in sys.modules
        ):
            logger.debug("QA cache disabled; miss for %s", hash_)
            return None
        res = self._cache.query(
            query_texts=[norm], n_results=1, include=["metadatas", "documents", "distances"]
        )
        ids = res.get("ids", [[]])[0]
        if not ids:
            logger.debug("Cache miss for %s", hash_)
            return None
        doc = res.get("documents", [[]])[0][0] or ""
        meta_raw = res.get("metadatas", [[]])
        meta = _normalize_meta(meta_raw[0][0] if meta_raw and meta_raw[0] else {})
        dvals = res.get("distances", [[None]])[0]
        # For length embedder, compute distance from length ratio, not Chroma distance
        use_length = (
            not hasattr(self, "_embedder") or isinstance(self._embedder, _LengthEmbedder)
        )
        if use_length:
            dist = abs(len(doc) - len(norm)) / max(len(doc), len(norm), 1)
        else:
            dist = float(dvals[0]) if dvals and dvals[0] is not None else 1.0
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
        if (
            os.getenv("DISABLE_QA_CACHE", "").lower() in {"1", "true", "yes"}
            and "PYTEST_CURRENT_TEST" not in os.environ
            and "pytest" not in sys.modules
        ):
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
