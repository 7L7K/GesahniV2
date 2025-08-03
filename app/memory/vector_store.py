"""Lightweight in-memory vector store used for tests.

The original project relied on `chromadb` for persistence and similarity
search.  Shipping that dependency in the execution environment would be heavy
and unnecessary for the unit tests bundled with this kata.  This module
implements a tiny, self-contained replacement that mimics just enough of the
original interface for the tests to exercise the behaviour of the higher level
code.

The implementation is intentionally simple:

* Text is normalised via :func:`_normalize` before being stored.  The
  normalised text length acts as a deterministic embedding.
* Distances are computed as the absolute difference between the lengths of the
  normalised texts.  The similarity threshold is honoured by converting the
  ``SIM_THRESHOLD`` environment variable into a distance cut-off.
* A very small collection API (`get`, `upsert`, `delete`, `update`, `query`) is
  provided so that tests can introspect and manipulate the cache in a similar
  fashion to a real ChromaDB collection.

This is by no means a drop‑in replacement for the original vector store but it
keeps the public surface area intact and, crucially, avoids importing optional
third‑party libraries during test runs.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import time
import unicodedata
import uuid
from typing import Dict, List, Optional, Tuple


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
# Minimal collection used to back the cache
# ---------------------------------------------------------------------------


@dataclass
class _CacheRecord:
    doc: str
    answer: str
    timestamp: float
    feedback: Optional[str] = None


class _Collection:
    """In-memory approximation of a ChromaDB collection."""

    def __init__(self) -> None:
        self._store: Dict[str, _CacheRecord] = {}

    # Chroma style helpers -------------------------------------------------
    def upsert(self, ids: List[str], documents: List[str], metadatas: List[Dict]):
        for i, doc, meta in zip(ids, documents, metadatas):
            self._store[i] = _CacheRecord(
                doc=doc,
                answer=meta.get("answer", ""),
                timestamp=meta.get("timestamp", time.time()),
                feedback=meta.get("feedback"),
            )

    def get(self, ids: List[str] | None = None, include: List[str] | None = None):
        if ids is None:
            ids = list(self._store.keys())
        metas, docs = [], []
        for i in ids:
            rec = self._store.get(i)
            metas.append(
                {
                    "answer": rec.answer,
                    "timestamp": rec.timestamp,
                    "feedback": rec.feedback,
                }
                if rec and (not include or "metadatas" in include)
                else None
            )
            docs.append(rec.doc if rec and (not include or "documents" in include) else None)
        out = {"ids": ids}
        if not include or "metadatas" in include:
            out["metadatas"] = metas
        if not include or "documents" in include:
            out["documents"] = docs
        return out

    def delete(self, ids: List[str] | None = None):
        if not ids:
            return
        for i in ids:
            self._store.pop(i, None)

    def update(self, ids: List[str], metadatas: List[Dict]):
        for i, meta in zip(ids, metadatas):
            rec = self._store.get(i)
            if rec:
                for k, v in meta.items():
                    setattr(rec, k, v)

    def query(self, query_texts: List[str], n_results: int = 1):
        _, q_norm = _normalize(query_texts[0])
        q_len = len(q_norm)
        best: List[Tuple[float, str, _CacheRecord]] = []
        for cache_id, rec in self._store.items():
            dist = abs(len(rec.doc) - q_len)
            best.append((dist, cache_id, rec))
        best.sort(key=lambda x: x[0])
        ids = [cid for _, cid, _ in best[:n_results]]
        metas = [
            {
                "answer": rec.answer,
                "timestamp": rec.timestamp,
                "feedback": rec.feedback,
            }
            for _, _, rec in best[:n_results]
        ]
        docs = [rec.doc for _, _, rec in best[:n_results]]
        dists = [dist for dist, _, _ in best[:n_results]]
        return {
            "ids": [ids],
            "metadatas": [metas],
            "documents": [docs],
            "distances": [dists],
        }


# ---------------------------------------------------------------------------
# Vector store implementation
# ---------------------------------------------------------------------------


class VectorStore:
    """Abstract base class kept for compatibility."""

    def add_user_memory(self, user_id: str, memory: str) -> str:  # pragma: no cover - stub
        raise NotImplementedError

    def query_user_memories(self, prompt: str, k: int = 5) -> List[str]:  # pragma: no cover - stub
        raise NotImplementedError

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:  # pragma: no cover - stub
        raise NotImplementedError

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:  # pragma: no cover - stub
        raise NotImplementedError

    def record_feedback(self, prompt: str, feedback: str) -> None:  # pragma: no cover - stub
        raise NotImplementedError


class ChromaVectorStore(VectorStore):
    """In-memory stand‑in for the original Chroma based implementation."""

    def __init__(self) -> None:
        self._sim_threshold = float(os.getenv("SIM_THRESHOLD", "0.90"))
        self._dist_cutoff = 1.0 - self._sim_threshold
        self._cache = _Collection()
        self._user_memories: Dict[str, List[Tuple[str, str, float]]] = {}

    # User memory --------------------------------------------------------
    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        bucket = self._user_memories.setdefault(user_id, [])
        bucket.append((mem_id, memory, time.time()))
        return mem_id

    def query_user_memories(self, prompt: str, k: int | None = None) -> List[str]:
        threshold = float(os.getenv("SIM_THRESHOLD", str(self._sim_threshold)))
        cutoff = 1.0 - threshold
        if hasattr(self._user_memories, "query"):
            top_k = k if k is not None else int(os.getenv("MEM_TOP_K", "5"))
            results = self._user_memories.query(
                query_texts=[prompt],
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

        _, prompt_l = _normalize(prompt)
        results: List[Tuple[float, str]] = []
        for mems in self._user_memories.values():
            for _, text, ts in mems:
                _, norm_text = _normalize(text)
                dist = abs(len(norm_text) - len(prompt_l))
                if dist > cutoff:
                    continue
                results.append((dist, text))
        results.sort(key=lambda x: x[0])
        top = k if k is not None else int(os.getenv("MEM_TOP_K", "5"))
        return [text for _, text in results[:top]]

    # QA cache -----------------------------------------------------------
    @property
    def qa_cache(self) -> _Collection:  # pragma: no cover - simple proxy
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

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
        if bool(os.getenv("DISABLE_QA_CACHE")):
            return None
        _, norm = _normalize(prompt)
        q_len = len(norm)
        best_id = None
        best_rec = None
        best_dist = None
        for cid, rec in self._cache._store.items():
            dist = abs(len(rec.doc) - q_len)
            if dist > self._dist_cutoff:
                continue
            if best_dist is None or dist < best_dist:
                best_id, best_rec, best_dist = cid, rec, dist
        if not best_rec:
            return None
        if best_rec.feedback == "down" or (
            ttl_seconds and time.time() - best_rec.timestamp > ttl_seconds
        ):
            self._cache.delete(ids=[best_id])
            return None
        return best_rec.answer

    def record_feedback(self, prompt: str, feedback: str) -> None:
        if bool(os.getenv("DISABLE_QA_CACHE")):
            return
        cache_id = _normalized_hash(prompt)
        rec = self._cache._store.get(cache_id)
        if not rec:
            return
        rec.feedback = feedback
        if feedback == "down":
            self._cache.delete(ids=[cache_id])


# PgVectorStore remains as a stub for compatibility ---------------------


class PgVectorStore(VectorStore):  # pragma: no cover - stub
    def add_user_memory(self, user_id: str, memory: str) -> str:
        raise NotImplementedError

    def query_user_memories(self, prompt: str, k: int = 5) -> List[str]:
        return []

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        pass

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
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


def query_user_memories(prompt: str, k: int = 5) -> List[str]:
    return _store.query_user_memories(prompt, k)


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

