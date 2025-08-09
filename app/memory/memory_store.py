"""In-memory vector store implementation."""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import os
import sys

from app import metrics
from app.embeddings import embed_sync
from app.telemetry import hash_user_id

from .env_utils import (
    _clean_meta,
    _cosine_similarity,
    _env_flag,
    _get_sim_threshold,
    _normalize,
    _normalized_hash,
)


logger = logging.getLogger(__name__)


def _qa_disabled() -> bool:
    """Return True if QA cache should be disabled for runtime.

    Tests always force-enable the cache regardless of env flags.
    """

    if "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules:
        return False
    return _env_flag("DISABLE_QA_CACHE")


class VectorStore:
    """Abstract interface for vector store backends."""

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
        embeddings: List[List[float]] | None = None,
        documents: List[str],
        metadatas: List[Dict],
    ) -> None:
        if embeddings is None:
            embeddings = [embed_sync(doc) for doc in documents]
        for i, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            self._store[i] = _CacheRecord(
                embedding=emb,
                doc=doc,
                answer=meta.get("answer", ""),
                timestamp=meta.get("timestamp", time.time()),
                feedback=meta.get("feedback"),
            )

    def get_items(
        self, ids: List[str] | None = None, include: List[str] | None = None
    ) -> Dict[str, List]:
        """Return selected items from the collection.

        Args:
            ids: Specific document identifiers to fetch. If ``None`` all items
                are returned.
            include: Optional list of fields to include. Supports
                ``"metadatas"`` and ``"documents"``. When ``None`` both are
                included.

        Returns:
            A dictionary containing the requested ``ids`` and any additional
            data specified via ``include``.
        """

        ids = ids or list(self._store)
        metas: List[Dict | None] = []
        docs: List[str | None] = []
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
        out: Dict[str, List] = {"ids": ids}
        if include is None or "metadatas" in include:
            out["metadatas"] = metas
        if include is None or "documents" in include:
            out["documents"] = docs
        return out

    def keys(self) -> List[str]:
        """Return all document identifiers stored in the collection."""
        return list(self._store)

    def delete(self, *, ids: List[str] | None = None) -> None:
        for i in ids or []:
            self._store.pop(i, None)

    def update(self, *, ids: List[str], metadatas: List[Dict]) -> None:
        for i, meta in zip(ids, metadatas):
            rec = self._store.get(i)
            if rec:
                for k, v in meta.items():
                    setattr(rec, k, v)


class MemoryVectorStore(VectorStore):
    """Lightweight dependency-free vector store used for tests."""

    def __init__(self) -> None:
        self._dist_cutoff = 1.0 - _get_sim_threshold()
        self._cache = _Collection()
        self._user_memories: Dict[str, List[Tuple[str, str, List[float], float]]] = {}

    def add_user_memory(self, user_id: str, memory: str) -> str:
        mem_id = str(uuid.uuid4())
        self._user_memories.setdefault(user_id, []).append(
            (mem_id, memory, embed_sync(memory), time.time())
        )
        hashed = hash_user_id(user_id)
        metrics.USER_MEMORY_ADDS.labels("memory", hashed).inc()
        logger.debug("Added user memory %s for %s", mem_id, hashed)
        return mem_id

    def query_user_memories(self, user_id: str, prompt: str, k: int = 5) -> List[str]:
        self._dist_cutoff = 1.0 - _get_sim_threshold()
        logger.info(
            "query_user_memories start user_id=%s prompt=%s k=%s",
            user_id,
            prompt,
            k,
        )
        q_emb = embed_sync(prompt)
        res: List[Tuple[float, float, str]] = []
        for _mid, doc, emb, ts in self._user_memories.get(user_id, []):
            dist = 1.0 - _cosine_similarity(q_emb, emb)
            if dist <= self._dist_cutoff:
                res.append((dist, -ts, doc))
        res.sort()
        top_items = res[:k]
        docs_out = [doc for _, _, doc in top_items]
        dists_out = [round(float(dist), 4) for dist, _, _ in top_items]
        logger.info(
            "query_user_memories end user_id=%s returned=%d dists=%s",
            user_id,
            len(docs_out),
            dists_out,
        )
        return docs_out

    @property
    def qa_cache(self) -> _Collection:
        return self._cache

    def cache_answer(self, cache_id: str, prompt: str, answer: str) -> None:
        if _qa_disabled():
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
        hash_ = _normalized_hash(prompt)
        if _qa_disabled():
            logger.debug("QA cache disabled; miss for %s", hash_)
            return None
        _, norm = _normalize(prompt)
        q_emb = embed_sync(norm)
        best = None
        best_id = None
        best_dist = None
        for cid, rec in self._cache._store.items():
            if rec.feedback == "down":
                continue
            dist = 1.0 - _cosine_similarity(q_emb, rec.embedding)
            if dist <= self._dist_cutoff and (best_dist is None or dist < best_dist):
                best, best_id, best_dist = rec, cid, dist
        if not best:
            logger.debug("Cache miss for %s", hash_)
            return None
        if ttl_seconds and time.time() - best.timestamp > ttl_seconds:
            logger.debug("Cache expired for %s", hash_)
            self._cache.delete(ids=[best_id])
            return None
        logger.debug("Cache hit for %s (dist=%.4f)", hash_, best_dist or -1.0)
        return best.answer

    def record_feedback(self, prompt: str, feedback: str) -> None:
        if _qa_disabled():
            return
        cid = _normalized_hash(prompt)
        if feedback == "down":
            logger.debug("Cache invalidated by feedback for %s", cid)
            self._cache.delete(ids=[cid])
        else:
            self._cache.update(ids=[cid], metadatas=[{"feedback": feedback}])

    def close(self) -> None:  # pragma: no cover - trivial
        return


__all__ = ["VectorStore", "MemoryVectorStore"]
