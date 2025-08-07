"""Unified vector store module.

Supports two back‑ends:
1. **MemoryVectorStore** – lightweight, dependency‑free store for unit tests that mimics the minimal ChromaDB surface.
2. **ChromaVectorStore** – production store backed by `chromadb.PersistentClient`.

Environment flags:
- `VECTOR_STORE`: `memory`/`inmemory` to force test store, else uses Chroma.
- `SIM_THRESHOLD`: cosine similarity threshold (default 0.90).
- `DISABLE_QA_CACHE`: truthy value disables all QA‑cache operations.
- `CHROMA_PATH`: filesystem path for Chroma DB (default `.chromadb`).
"""

from __future__ import annotations

import hashlib
import os
import time
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import chromadb
from app.embeddings import embed_sync

# ---------------------------------------------------------------------------
# Environment helpers
# ---------------------------------------------------------------------------


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


# ---------------------------------------------------------------------------
# Normalization & helpers
# ---------------------------------------------------------------------------


def _normalize(text: str) -> Tuple[str, str]:
    norm = unicodedata.normalize("NFKD", text)
    for bad, good in {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
    }.items():
        norm = norm.replace(bad, good)
    norm = " ".join(norm.split()).lower()
    h = hashlib.sha256(norm.encode()).hexdigest()
    return h, norm


def _normalized_hash(prompt: str) -> str:
    return _normalize(prompt)[0]


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    a_arr, b_arr = np.array(a), np.array(b)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    return float(np.dot(a_arr, b_arr) / denom) if denom else 0.0


# ---------------------------------------------------------------------------
# Tiny length-based embedder for Chroma
# ---------------------------------------------------------------------------


class _LengthEmbedder:
    def __call__(self, input: Sequence[str]) -> List[List[float]]:
        return [[float(len(_normalize(t)[1]))] for t in input]

    def name(self) -> str:  # pragma: no cover - simple helper for Chroma
        """Return a stable name used by Chroma to identify the embedder."""
        return "length-embedder"


# ---------------------------------------------------------------------------
# In-memory store (test back-end)
# ---------------------------------------------------------------------------


@dataclass
class _CacheRecord:
    embedding: List[float]
    doc: str
    answer: str
    timestamp: float
    feedback: Optional[str] = None


class _Collection:
    def __init__(self) -> None:
        self._store: Dict[str, _CacheRecord] = {}

    def upsert(
        self,
        *,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict],
    ) -> None:
        for i, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            self._store[i] = _CacheRecord(
                embedding=emb,
                doc=doc,
                answer=meta.get("answer", ""),
                timestamp=meta.get("timestamp", time.time()),
                feedback=meta.get("feedback"),
            )

    def get(
        self, *, ids: List[str] | None = None, include: List[str] | None = None
    ) -> Dict[str, List]:
        ids = ids or list(self._store)
        metas, docs = [], []
        for i in ids:
            rec = self._store.get(i)
            metas.append(
                {
                    "answer": rec.answer,
                    "timestamp": rec.timestamp,
                    "feedback": rec.feedback,
                }
                if rec and (include is None or "metadatas" in include)
                else None
            )
            docs.append(
                rec.doc if rec and (include is None or "documents" in include) else None
            )
        out = {"ids": ids}
        if include is None or "metadatas" in include:
            out["metadatas"] = metas
        if include is None or "documents" in include:
            out["documents"] = docs
        return out

    def delete(self, *, ids: List[str] | None = None) -> None:
        for i in ids or []:
            self._store.pop(i, None)

    def update(self, *, ids: List[str], metadatas: List[Dict]) -> None:
        for i, meta in zip(ids, metadatas):
            rec = self._store.get(i)
            if rec:
                for k, v in meta.items():
                    setattr(rec, k, v)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------


class VectorStore:
    def add_user_memory(self, user_id: str, memory: str) -> str: ...
    def query_user_memories(
        self, user_id: str, prompt: str, k: int = 5
    ) -> List[str]: ...
    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None: ...
    def lookup_cached_answer(
        self, prompt: str, ttl_seconds: int = 86400
    ) -> Optional[str]: ...
    def record_feedback(self, prompt: str, feedback: str) -> None: ...
    def close(self) -> None: ...


# ---------------------------------------------------------------------------
# MemoryVectorStore
# ---------------------------------------------------------------------------


class MemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        self._dist_cutoff = 1.0 - float(os.getenv("SIM_THRESHOLD", "0.90"))
        self._cache = _Collection()
        self._user_memories: Dict[str, List[Tuple[str, str, List[float], float]]] = {}

    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        self._user_memories.setdefault(user_id, []).append(
            (mem_id, memory, embed_sync(memory), time.time())
        )
        return mem_id

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
        q_emb = embed_sync(prompt)
        res: List[Tuple[float, float, str]] = []
        for _mid, doc, emb, ts in self._user_memories.get(user_id, []):
            dist = 1.0 - _cosine_similarity(q_emb, emb)
            if dist <= self._dist_cutoff:
                res.append((dist, -ts, doc))
        res.sort()
        return [doc for _, _, doc in res[:k]]

    @property
    def qa_cache(self) -> _Collection:
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        if _env_flag("DISABLE_QA_CACHE"):
            return
        _, norm = _normalize(prompt)
        self._cache.upsert(
            ids=[cache_id],
            embeddings=[embed_sync(norm)],
            documents=[norm],
            metadatas=[{"answer": answer, "timestamp": time.time(), "feedback": None}],
        )

    def lookup_cached_answer(
        self, prompt: str, ttl_seconds: int = 86400
    ) -> Optional[str]:
        if _env_flag("DISABLE_QA_CACHE"):
            return None
        _, norm = _normalize(prompt)
        q_emb = embed_sync(norm)
        best = None
        best_dist = None
        for cid, rec in self._cache._store.items():
            if rec.feedback == "down":
                continue
            dist = 1.0 - _cosine_similarity(q_emb, rec.embedding)
            if dist <= self._dist_cutoff and (best_dist is None or dist < best_dist):
                best, best_dist = rec, dist
        if not best:
            return None
        if ttl_seconds and time.time() - best.timestamp > ttl_seconds:
            self._cache.delete(ids=[cid])
            return None
        return best.answer

    def record_feedback(self, prompt: str, feedback: str) -> None:
        if _env_flag("DISABLE_QA_CACHE"):
            return
        cid = _normalized_hash(prompt)
        if feedback == "down":
            self._cache.delete(ids=[cid])
        else:
            self._cache.update(ids=[cid], metadatas=[{"feedback": feedback}])

    def close(self) -> None:  # pragma: no cover - trivial
        """No-op for compatibility with :class:`ChromaVectorStore`."""
        return


# ---------------------------------------------------------------------------
# ChromaVectorStore
# ---------------------------------------------------------------------------


class ChromaVectorStore(VectorStore):
    def __init__(self) -> None:
        self._dist_cutoff = 1.0 - float(os.getenv("SIM_THRESHOLD", "0.90"))
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
        self._user_memories.upsert(
            ids=[mem_id],
            documents=[memory],
            metadatas=[{"user_id": user_id, "ts": time.time()}],
        )
        return mem_id

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
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
    def qa_cache(self):
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        if _env_flag("DISABLE_QA_CACHE"):
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
        if _env_flag("DISABLE_QA_CACHE"):
            return None
        res = self._cache.query(
            query_texts=[prompt], n_results=1, include=["metadatas", "distances"]
        )
        ids = res.get("ids", [[]])[0]
        if not ids:
            return None
        dist = float(res.get("distances", [[]])[0][0])
        meta = res.get("metadatas", [[]])[0][0] or {}
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
        if _env_flag("DISABLE_QA_CACHE"):
            return
        cid = _normalized_hash(prompt)
        self._cache.update(ids=[cid], metadatas=[{"feedback": feedback}])
        if feedback == "down":
            self._cache.delete(ids=[cid])

    def close(self) -> None:  # pragma: no cover - thin wrapper
        """Dispose of the underlying Chroma client."""
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
        except Exception:
            pass
        self._client = None


# ---------------------------------------------------------------------------
# Module-level API
# ---------------------------------------------------------------------------


def _get_store() -> VectorStore:
    return (
        MemoryVectorStore()
        if os.getenv("VECTOR_STORE", "").lower() in ("memory", "inmemory")
        else ChromaVectorStore()
    )


_store: VectorStore = _get_store()


def add_user_memory(user_id: str, memory: str) -> str:
    return _store.add_user_memory(user_id, memory)


def query_user_memories(user_id: str, prompt: str, k: int = 5) -> List[str]:
    return _store.query_user_memories(user_id, prompt, k)


def cache_answer(prompt: str, answer: str, cache_id: str | None = None) -> None:
    cid = cache_id or _normalized_hash(prompt)
    _store.cache_answer(cid, prompt, answer)


def cache_answer_legacy(*args) -> None:
    if len(args) == 2:
        cache_answer(args[0], args[1])
    elif len(args) == 3:
        cache_answer(args[1], args[2], args[0])
    else:
        raise TypeError("cache_answer expects 2 or 3 arguments")


def lookup_cached_answer(prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
    return _store.lookup_cached_answer(prompt, ttl_seconds)


def record_feedback(prompt: str, feedback: str) -> None:
    return _store.record_feedback(prompt, feedback)


def invalidate_cache(prompt: str) -> None:
    _store.qa_cache.delete(ids=[_normalized_hash(prompt)])


def close_store() -> None:
    """Close and reset the global vector store."""
    global _store
    if _store is not None:
        try:
            _store.close()
        finally:
            _store = _get_store()


__all__ = [
    "add_user_memory",
    "query_user_memories",
    "cache_answer",
    "cache_answer_legacy",
    "lookup_cached_answer",
    "record_feedback",
    "invalidate_cache",
    "close_store",
    "VectorStore",
    "MemoryVectorStore",
    "ChromaVectorStore",
]
