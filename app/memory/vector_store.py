from __future__ import annotations

import os
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.config import Settings
from chromadb.utils.embedding_functions import EmbeddingFunction

from .. import embeddings


class VectorStore(ABC):
    """Abstract VectorStore interface."""

    @abstractmethod
    def add_user_memory(self, user_id: str, memory: str) -> str: ...

    @abstractmethod
    def query_user_memories(self, prompt: str, k: int = 5) -> List[str]: ...

    @abstractmethod
    def cache_answer(self, *args: str) -> None: ...

    @abstractmethod
    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]: ...

    @abstractmethod
    def record_feedback(self, prompt: str, feedback: str) -> None: ...


class _EmbeddingFunction(EmbeddingFunction):
    """Embedding function backed by OpenAI's text-embedding-3-small."""

    def __call__(self, texts: List[str]) -> List[List[float]]:  # pragma: no cover - sync wrapper
        return [embeddings.embed_sync(t) for t in texts]


class _SafeCollection:
    """Wrapper around a ChromaDB collection that tolerates empty deletes."""

    def __init__(self, col):
        self._col = col

    def delete(self, ids=None, **kwargs):
        if not ids:
            return
        return self._col.delete(ids=ids, **kwargs)

    def __getattr__(self, name):  # pragma: no cover - simple proxy
        return getattr(self._col, name)


class ChromaVectorStore(VectorStore):
    def __init__(self) -> None:
        settings = Settings(anonymized_telemetry=False)
        data = Path("data")
        final = data / "chroma"
        tmp = data / "chroma_tmp"
        if final.exists():
            client = chromadb.PersistentClient(path=str(final), settings=settings)
        else:
            tmp.mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=str(tmp), settings=settings)
            os.replace(tmp, final)
            client = chromadb.PersistentClient(path=str(final), settings=settings)
        self._client = client
        self._user_memories = self._client.get_or_create_collection(
            "user_memories", embedding_function=_EmbeddingFunction()
        )
        self._qa_cache = _SafeCollection(
            self._client.get_or_create_collection(
                "qa_cache", embedding_function=_EmbeddingFunction()
            )
        )

    # ─── USER MEMORIES ────────────────────────────────────────────────────────
    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        self._user_memories.add(
            ids=[mem_id],
            documents=[memory],
            metadatas=[{"user_id": user_id, "ts": time.time()}],
        )
        return mem_id

    def query_user_memories(self, prompt: str, k: int = 5) -> List[str]:
        results = self._user_memories.query(
            query_texts=[prompt], n_results=k, include=["documents", "distances", "metadatas"]
        )
        docs = results.get("documents", [[]])[0]
        dists = results.get("distances", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        items = []
        for doc, dist, meta in zip(docs, dists, metas):
            if not doc:
                continue
            sim = 1.0 - float(dist)
            if sim < 0.80:
                continue
            ts = float((meta or {}).get("ts", 0))
            items.append({"doc": doc, "sim": sim, "ts": ts})
        items.sort(key=lambda x: (-x["sim"], -x["ts"]))
        return [it["doc"] for it in items[:3]]

    # ─── QA CACHE ─────────────────────────────────────────────────────────────
    def _cache_disabled(self) -> bool:
        return bool(os.getenv("DISABLE_QA_CACHE"))

    def cache_answer(self, *args: str) -> None:
        if self._cache_disabled():
            return
        if len(args) == 2:
            cache_id, prompt, answer = args[0], args[0], args[1]
        elif len(args) == 3:
            cache_id, prompt, answer = args
        else:
            raise TypeError("cache_answer expects 2 or 3 string arguments")
        self._qa_cache.upsert(
            ids=[cache_id],
            documents=[prompt],
            metadatas=[{"answer": answer, "timestamp": time.time(), "feedback": None}],
        )

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
        if self._cache_disabled():
            return None
        result = self.qa_cache.query(query_texts=[prompt], n_results=1)
        ids = result.get("ids", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        if not ids or not metas:
            return None
        cache_id = ids[0]
        meta = metas[0] or {}
        answer = meta.get("answer")
        fb = meta.get("feedback")
        ts = meta.get("timestamp", 0)
        if fb == "down" or (ts and time.time() - ts > ttl_seconds):
            try:
                self._qa_cache.delete(ids=[cache_id])
            finally:
                return None
        return answer

    def record_feedback(self, prompt: str, feedback: str) -> None:
        if self._cache_disabled():
            return
        result = self.qa_cache.query(query_texts=[prompt], n_results=1)
        ids = result.get("ids", [[]])[0]
        if not ids:
            return
        cache_id = ids[0]
        self._qa_cache.update(ids=[cache_id], metadatas=[{"feedback": feedback}])
        if feedback == "down":
            try:
                self._qa_cache.delete(ids=[cache_id])
            except Exception:  # pragma: no cover - best effort
                pass


class PgVectorStore(VectorStore):  # pragma: no cover - stub implementation
    def add_user_memory(self, user_id: str, memory: str) -> str:
        raise NotImplementedError

    def query_user_memories(self, prompt: str, k: int = 5) -> List[str]:
        return []

    def cache_answer(self, *args: str) -> None:
        pass

    def lookup_cached_answer(self, prompt: str, ttl_seconds: int = 86400) -> Optional[str]:
        return None

    def record_feedback(self, prompt: str, feedback: str) -> None:
        pass


def _get_store() -> VectorStore:
    backend = os.getenv("VECTOR_STORE", "chroma").lower()
    if backend == "pgvector":
        return PgVectorStore()
    return ChromaVectorStore()


_store = _get_store()

add_user_memory = _store.add_user_memory
query_user_memories = _store.query_user_memories
cache_answer = _store.cache_answer
lookup_cached_answer = _store.lookup_cached_answer
record_feedback = _store.record_feedback

__all__ = [
    "add_user_memory",
    "query_user_memories",
    "cache_answer",
    "lookup_cached_answer",
    "record_feedback",
    "VectorStore",
    "ChromaVectorStore",
    "PgVectorStore",
]
