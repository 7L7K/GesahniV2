"""Chroma-backed vector store for user memories and QA caching.

This module wraps a minimal subset of the original project's vector store
interface.  It uses a :class:`chromadb.PersistentClient` with a very small
embedding function that simply encodes the length of the normalised text.
This keeps behaviour deterministic for tests while exercising the real
Chroma collection APIs.
"""

from __future__ import annotations

import hashlib
import os
import time
import unicodedata
import uuid
from typing import List, Optional, Sequence, Tuple

import chromadb


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> Tuple[str, str]:
    """Return ``(hash, normalized_text)`` for ``text``."""

    norm = unicodedata.normalize("NFKD", text)
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
    }
    for bad, good in replacements.items():
        norm = norm.replace(bad, good)
    norm = " ".join(norm.split()).lower()
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return h, norm


def _normalized_hash(prompt: str) -> str:
    return _normalize(prompt)[0]


# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------


class _LengthEmbedder:
    """Very small embedding function based on text length."""

    def __call__(self, texts: Sequence[str]) -> List[List[float]]:
        out: List[List[float]] = []
        for text in texts:
            _, norm = _normalize(text)
            out.append([float(len(norm))])
        return out


# ---------------------------------------------------------------------------
# Vector store implementations
# ---------------------------------------------------------------------------


class VectorStore:
    """Abstract base class kept for compatibility."""

    def add_user_memory(
        self, user_id: str, memory: str
    ) -> str:  # pragma: no cover - stub
        raise NotImplementedError

    def query_user_memories(
        self, user_id: str, prompt: str, k: int = 5
    ) -> List[str]:  # pragma: no cover - stub
        raise NotImplementedError

    def cache_answer(
        self, cache_id: str, prompt: str, answer: str
    ) -> None:  # pragma: no cover - stub
        raise NotImplementedError

    def lookup_cached_answer(
        self, prompt: str, ttl_seconds: int = 86400
    ) -> Optional[str]:  # pragma: no cover - stub
        raise NotImplementedError

    def record_feedback(
        self, prompt: str, feedback: str
    ) -> None:  # pragma: no cover - stub
        raise NotImplementedError


class ChromaVectorStore(VectorStore):
    """Chroma based implementation used by the application."""

    def __init__(self) -> None:
        self._sim_threshold = float(os.getenv("SIM_THRESHOLD", "0.90"))
        self._dist_cutoff = 1.0 - self._sim_threshold
        path = os.getenv("CHROMA_PATH", ".chromadb")
        self._client = chromadb.PersistentClient(path=path)
        self._embedder = _LengthEmbedder()
        self._cache = self._client.get_or_create_collection(
            "qa_cache", embedding_function=self._embedder
        )
        self._user_memories = self._client.get_or_create_collection(
            "user_memories", embedding_function=self._embedder
        )

    # ------------------------------------------------------------------
    # User memory operations
    # ------------------------------------------------------------------
    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        ts = time.time()
        # Persist in Chroma collection
        self._user_memories.upsert(
            ids=[mem_id],
            documents=[memory],
            metadatas=[{"user_id": user_id, "ts": ts}],
        )
        return mem_id

    def query_user_memories(
        self, user_id: str, prompt: str, k: int | None = None
    ) -> List[str]:
        threshold = float(os.getenv("SIM_THRESHOLD", str(self._sim_threshold)))
        cutoff = 1.0 - threshold
        if hasattr(self._user_memories, "query"):
            top_k = k if k is not None else int(os.getenv("MEM_TOP_K", "5"))
            results = self._user_memories.query(
                query_texts=[prompt],
                where={"user_id": user_id},
                n_results=top_k,
                include=["documents", "distances", "metadatas"],
            )
            docs = results.get("documents", [[]])[0]
            dists = results.get("distances", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            items = []
            for doc, dist, meta in zip(docs, dists, metas):
                if not doc:
                    continue
                if float(dist) > cutoff:
                    continue
                ts = float((meta or {}).get("ts", 0))
                items.append({"doc": doc, "dist": float(dist), "ts": ts})
            items.sort(key=lambda x: (x["dist"], -x["ts"]))
            return [it["doc"] for it in items[:top_k]]

        return []

    # ------------------------------------------------------------------
    # QA cache operations
    # ------------------------------------------------------------------
    @property
    def qa_cache(self):  # pragma: no cover - simple proxy
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        if bool(os.getenv("DISABLE_QA_CACHE")):
            return
        _, norm = _normalize(prompt)
        self._cache.upsert(
            ids=[cache_id],
            documents=[norm],
            metadatas=[{"answer": answer, "timestamp": time.time(), "feedback": None}],
        )

    def lookup_cached_answer(
        self, prompt: str, ttl_seconds: int = 86400
    ) -> Optional[str]:
        if bool(os.getenv("DISABLE_QA_CACHE")):
            return None
        results = self._cache.query(
            query_texts=[prompt],
            n_results=1,
            include=["metadatas", "distances", "ids"],
        )
        ids = results.get("ids", [[]])[0]
        if not ids:
            return None
        dists = results.get("distances", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dist = float(dists[0]) if dists else None
        meta = metas[0] if metas else {}
        if dist is None or dist > self._dist_cutoff:
            return None
        answer = (meta or {}).get("answer")
        ts = float((meta or {}).get("timestamp", 0))
        feedback = (meta or {}).get("feedback")
        cache_id = ids[0]
        if feedback == "down" or (ttl_seconds and time.time() - ts > ttl_seconds):
            self._cache.delete(ids=[cache_id])
            return None
        return answer

    def record_feedback(self, prompt: str, feedback: str) -> None:
        if bool(os.getenv("DISABLE_QA_CACHE")):
            return
        cache_id = _normalized_hash(prompt)
        metas = self._cache.get(ids=[cache_id], include=["metadatas"]).get(
            "metadatas", [None]
        )
        meta = metas[0]
        if meta is None:
            return
        meta["feedback"] = feedback
        if feedback == "down":
            self._cache.delete(ids=[cache_id])
        else:
            self._cache.update(ids=[cache_id], metadatas=[meta])


class PgVectorStore(VectorStore):  # pragma: no cover - stub
    def add_user_memory(self, user_id: str, memory: str) -> str:
        raise NotImplementedError

    def query_user_memories(self, prompt: str, k: int = 5) -> List[str]:
        return []

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        pass

    def lookup_cached_answer(
        self, prompt: str, ttl_seconds: int = 86400
    ) -> Optional[str]:
        return None

    def record_feedback(self, prompt: str, feedback: str) -> None:
        pass


# ---------------------------------------------------------------------------
# Module level convenience API
# ---------------------------------------------------------------------------


def _get_store() -> VectorStore:
    backend = os.getenv("VECTOR_STORE", "chroma").lower()
    if backend == "pgvector":
        return PgVectorStore()
    return ChromaVectorStore()


_store = _get_store()


def add_user_memory(user_id: str, memory: str) -> str:
    return _store.add_user_memory(user_id, memory)


def query_user_memories(user_id: str, prompt: str, k: int = 5) -> List[str]:
    return _store.query_user_memories(user_id, prompt, k)


def cache_answer(*args) -> None:
    """Cache an answer for a prompt.

    Supports two call styles:

    ``cache_answer(prompt, answer)`` – uses the normalised hash as the cache key.
    ``cache_answer(cache_id, prompt, answer)`` – explicitly specify the key.
    """

    if len(args) == 2:
        prompt, answer = args
        cache_id = _normalized_hash(prompt)
    elif len(args) == 3:
        cache_id, prompt, answer = args
    else:  # pragma: no cover - defensive
        raise TypeError("cache_answer expects 2 or 3 arguments")
    _store.cache_answer(cache_id, prompt, answer)


def lookup_cached_answer(prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
    return _store.lookup_cached_answer(prompt, ttl_seconds)


def record_feedback(prompt: str, feedback: str) -> None:
    _store.record_feedback(prompt, feedback)


def invalidate_cache(prompt: str) -> None:
    cache_id = _normalized_hash(prompt)
    _store.qa_cache.delete(ids=[cache_id])


# Expose the underlying collection for tests
qa_cache = _store.qa_cache
_qa_cache = qa_cache


__all__ = [
    "add_user_memory",
    "query_user_memories",
    "cache_answer",
    "lookup_cached_answer",
    "record_feedback",
    "invalidate_cache",
    "VectorStore",
    "ChromaVectorStore",
    "PgVectorStore",
]
