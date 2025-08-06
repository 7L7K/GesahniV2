"""Unified vector store module.

Supports:
- MemoryVectorStore: lightweight in-memory store for unit tests, mimicking ChromaDB interface.
- ChromaVectorStore: production store using chromadb PersistentClient.
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
from app.embeddings import embed_sync
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


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Return the cosine similarity between two vectors."""
    a_arr = np.array(a)
    b_arr = np.array(b)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if denom == 0.0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / denom)

# ---------------------------------------------------------------------------
# Embedding helper
# ---------------------------------------------------------------------------

class _LengthEmbedder:
    """Very small embedding function based on text length."""

    def __call__(self, texts: Sequence[str]) -> List[List[float]]:
        return [[float(len(_normalize(text)[1]))] for text in texts]

# ---------------------------------------------------------------------------
# In-memory store for tests
# ---------------------------------------------------------------------------

@dataclass
class _CacheRecord:
    embedding: List[float]
    doc: str
    answer: str
    timestamp: float
    feedback: Optional[str] = None

class _Collection:
    """In-memory approximation of a ChromaDB collection."""

    def __init__(self) -> None:
        self._store: Dict[str, _CacheRecord] = {}

    def upsert(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict]
    ) -> None:
        for i, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            self._store[i] = _CacheRecord(
                embedding=emb,
                doc=doc,
                answer=meta.get("answer", ""),
                timestamp=meta.get("timestamp", time.time()),
                feedback=meta.get("feedback")
            )

    def get(
        self,
        ids: List[str] | None = None,
        include: List[str] | None = None
    ):
        if ids is None:
            ids = list(self._store.keys())
        metas, docs = [], []
        for i in ids:
            rec = self._store.get(i)
            if rec:
                if include is None or "metadatas" in include:
                    metas.append({"answer": rec.answer, "timestamp": rec.timestamp, "feedback": rec.feedback})
                if include is None or "documents" in include:
                    docs.append(rec.doc)
            else:
                if include is None or "metadatas" in include:
                    metas.append(None)
                if include is None or "documents" in include:
                    docs.append(None)
        result: Dict[str, List] = {"ids": ids}
        if include is None or "metadatas" in include:
            result["metadatas"] = metas
        if include is None or "documents" in include:
            result["documents"] = docs
        return result

    def delete(self, ids: List[str] | None = None) -> None:
        if not ids:
            return
        for i in ids:
            self._store.pop(i, None)

    def update(self, ids: List[str], metadatas: List[Dict]) -> None:
        for i, meta in zip(ids, metadatas):
            rec = self._store.get(i)
            if rec:
                for k, v in meta.items():
                    setattr(rec, k, v)

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
# In-memory implementation
# ---------------------------------------------------------------------------

class MemoryVectorStore(VectorStore):
    """Lightweight in-memory store for unit tests."""

    def __init__(self) -> None:
        self._sim_threshold = float(os.getenv("SIM_THRESHOLD", "0.90"))
        self._dist_cutoff = 1.0 - self._sim_threshold
        self._cache = _Collection()
        self._user_memories: Dict[str, List[Tuple[str, str, List[float], float]]] = {}

    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        embedding = embed_sync(memory)
        ts = time.time()
        self._user_memories.setdefault(user_id, []).append((mem_id, memory, embedding, ts))
        return mem_id

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
        top_k = k
        q_emb = embed_sync(prompt)
        results: List[Tuple[float, float, str]] = []
        for _id, doc, emb, ts in self._user_memories.get(user_id, []):
            sim = _cosine_similarity(q_emb, emb)
            dist = 1.0 - sim
            if dist > self._dist_cutoff:
                continue
            results.append((dist, -ts, doc))
        results.sort()
        return [doc for _, _, doc in results[:top_k]]

    @property
    def qa_cache(self) -> _Collection:
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        now = time.time()
        _, norm = _normalize(prompt)
        embedding = embed_sync(norm)
        self._cache.upsert(
            ids=[cache_id],
            embeddings=[embedding],
            documents=[norm],
            metadatas=[{"answer": answer, "timestamp": now, "feedback": None}],
        )

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
        best_id = None
        best_rec: Optional[_CacheRecord] = None
        best_dist: Optional[float] = None
        _, norm = _normalize(prompt)
        q_emb = embed_sync(norm)
        for cid, rec in self._cache._store.items():
            sim = _cosine_similarity(q_emb, rec.embedding)
            dist = 1.0 - sim
            if dist > self._dist_cutoff:
                continue
            if best_dist is None or dist < best_dist:
                best_id, best_rec, best_dist = cid, rec, dist
        if not best_rec:
            return None
        if best_rec.feedback == "down":
            self._cache.delete(ids=[best_id])
            return None
        if ttl_seconds and time.time() - best_rec.timestamp > ttl_seconds:
            self._cache.delete(ids=[best_id])
            return None
        return best_rec.answer

    def record_feedback(self, prompt: str, feedback: str) -> None:
        cache_id = _normalized_hash(prompt)
        self._cache.update(ids=[cache_id], metadatas=[{"feedback": feedback}])
        if feedback == "down":
            self._cache.delete(ids=[cache_id])

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
# Module-level store selection and API
# ---------------------------------------------------------------------------

def _get_store() -> VectorStore:
    backend = os.getenv("VECTOR_STORE", "chroma").lower()
    if backend in ("memory", "inmemory"):
        return MemoryVectorStore()
    return ChromaVectorStore()

_store: VectorStore = _get_store()


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
    "MemoryVectorStore",
    "ChromaVectorStore",
]
