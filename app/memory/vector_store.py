"""Chroma-backed vector store for user memories and QA caching.

This module wraps a minimal subset of the original project's vector store
interface. It uses a chromadb.PersistentClient with a very small embedding
function that simply encodes the length of the normalized text. This keeps
behavior deterministic for tests while exercising the real Chroma collection
APIs.
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
# Normalization helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> Tuple[str, str]:
    """Return (hash, normalized_text) for text."""
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
    """Hash of normalized prompt."""
    return _normalize(prompt)[0]

# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------

class _LengthEmbedder:
    """Very small embedding function based on text length."""

    def __call__(self, texts: Sequence[str]) -> List[List[float]]:
        return [[float(len(_normalize(text)[1]))] for text in texts]

# ---------------------------------------------------------------------------
# Vector store interface
# ---------------------------------------------------------------------------

class VectorStore:
    """Abstract base class for vector stores."""

    def add_user_memory(self, user_id: str, memory: str) -> str:
        raise NotImplementedError

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
        raise NotImplementedError

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        raise NotImplementedError

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
        raise NotImplementedError

    def record_feedback(self, prompt: str, feedback: str) -> None:
        raise NotImplementedError

# ---------------------------------------------------------------------------
# Chroma-based implementation
# ---------------------------------------------------------------------------

class ChromaVectorStore(VectorStore):
    """Chroma-based implementation for user memories and QA caching."""

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

    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        ts = time.time()
        self._user_memories.upsert(
            ids=[mem_id],
            documents=[memory],
            metadatas=[{"user_id": user_id, "ts": ts}],
        )
        return mem_id

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
        top_k = k
        results = self._user_memories.query(
            query_texts=[prompt],
            where={"user_id": user_id},
            n_results=top_k,
            include=["documents", "distances", "metadatas"],
        )
        docs = results.get("documents", [[]])[0]
        dists = results.get("distances", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        items: List[Tuple[float, float, str]] = []
        for doc, dist, meta in zip(docs, dists, metas):
            if not doc:
                continue
            if float(dist) > self._dist_cutoff:
                continue
            ts = float(meta.get("ts", 0))
            items.append((float(dist), -ts, doc))
        items.sort()
        return [doc for _, _, doc in items[:top_k]]

    @property
    def qa_cache(self):
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        now = time.time()
        _, norm = _normalize(prompt)
        self._cache.upsert(
            ids=[cache_id],
            documents=[norm],
            metadatas=[{"answer": answer, "timestamp": now, "feedback": None}],
        )

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
        results = self._cache.query(
            query_texts=[prompt],
            n_results=1,
            include=["metadatas", "distances", "ids"],
        )
        ids = results.get("ids", [[]])[0]
        if not ids:
            return None
        dist = float(results.get("distances", [[]])[0][0])
        meta = (results.get("metadatas", [[]])[0][0] or {})
        if dist > self._dist_cutoff:
            return None
        ts = float(meta.get("timestamp", 0))
        if ttl_seconds and time.time() - ts > ttl_seconds:
            self._cache.delete(ids=[ids[0]])
            return None
        if meta.get("feedback") == "down":
            self._cache.delete(ids=[ids[0]])
            return None
        return meta.get("answer")

    def record_feedback(self, prompt: str, feedback: str) -> None:
        cache_id = _normalized_hash(prompt)
        self._cache.update(ids=[cache_id], metadatas=[{"feedback": feedback}])
        if feedback == "down":
            self._cache.delete(ids=[cache_id])

# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------

_store = ChromaVectorStore()


def add_user_memory(user_id: str, memory: str) -> str:
    return _store.add_user_memory(user_id, memory)


def query_user_memories(user_id: str, prompt: str, k: int = 5) -> List[str]:
    return _store.query_user_memories(user_id, prompt, k)


def cache_answer(prompt: str, answer: str, cache_id: str | None = None) -> None:
    if cache_id is None:
        cache_id = _normalized_hash(prompt)
    _store.cache_answer(cache_id, prompt, answer)


def cache_answer_legacy(*args) -> None:
    if len(args) == 2:
        prompt, answer = args
        cache_answer(prompt=prompt, answer=answer)
    elif len(args) == 3:
        cache_id, prompt, answer = args
        cache_answer(prompt=prompt, answer=answer, cache_id=cache_id)
    else:
        raise TypeError("cache_answer expects 2 or 3 arguments")


def lookup_cached_answer(prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
    return _store.lookup_cached_answer(prompt, ttl_seconds)


def record_feedback(prompt: str, feedback: str) -> None:
    _store.record_feedback(prompt, feedback)


def invalidate_cache(prompt: str) -> None:
    cache_id = _normalized_hash(prompt)
    _store.qa_cache.delete(ids=[cache_id])

__all__ = [
    "add_user_memory",
    "query_user_memories",
    "cache_answer",
    "cache_answer_legacy",
    "lookup_cached_answer",
    "record_feedback",
    "invalidate_cache",
    "VectorStore",
    "ChromaVectorStore",
]
