"""High level vector store API used throughout the project."""

from __future__ import annotations

import logging
import os
import sys
from typing import List, Optional

from .chroma_store import ChromaVectorStore
from .env_utils import _normalized_hash
from .memory_store import MemoryVectorStore, VectorStore


logger = logging.getLogger(__name__)


def _get_store() -> VectorStore:
    """Return the configured vector store backend."""

    kind = os.getenv("VECTOR_STORE", "").lower()
    chroma_path = os.getenv("CHROMA_PATH", ".chroma_data")
    if kind in ("memory", "inmemory") or \
       "PYTEST_CURRENT_TEST" in os.environ or \
       "pytest" in sys.modules:
        logger.info("Using MemoryVectorStore (test mode or VECTOR_STORE=%s)", kind)
        return MemoryVectorStore()
    try:
        if not chroma_path:
            raise FileNotFoundError("CHROMA_PATH is empty")
        logger.info("Initializing ChromaVectorStore at path: %s", chroma_path)
        return ChromaVectorStore()
    except Exception as exc:
        if os.getenv("ENV", "").lower() == "production":
            logger.error("FATAL: ChromaVectorStore failed in production: %s", exc)
            raise
        logger.warning(
            "ChromaVectorStore unavailable at %s: %s; falling back to MemoryVectorStore",
            chroma_path,
            exc,
        )
        return MemoryVectorStore()


_store: VectorStore = _get_store()


def add_user_memory(user_id: str, memory: str) -> str:
    return _store.add_user_memory(user_id, memory)


def query_user_memories(user_id: str, prompt: str, k: int = 5) -> List[str]:
    return _store.query_user_memories(user_id, prompt, k)


def cache_answer(*args, **kwargs) -> None:
    if "prompt" in kwargs and "answer" in kwargs:
        prompt_val: str = kwargs["prompt"]
        answer_val: str = kwargs["answer"]
        cache_id_val: str | None = kwargs.get("cache_id")
    else:
        if len(args) == 2:
            prompt_val, answer_val = args  # type: ignore[assignment]
            cache_id_val = None
        elif len(args) == 3:
            cache_id_val, prompt_val, answer_val = args
        else:
            raise TypeError(
                "cache_answer expects (prompt, answer) or (cache_id, prompt, answer)"
            )
    cid = cache_id_val or _normalized_hash(prompt_val)
    _store.cache_answer(cid, prompt_val, answer_val)


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


class _QACacheProxy:
    def __call__(self):
        return _store.qa_cache

    def __getattr__(self, name):  # pragma: no cover - simple delegation
        return getattr(_store.qa_cache, name)


qa_cache = _QACacheProxy()
_qa_cache = qa_cache


def invalidate_cache(prompt: str) -> None:
    cid = _normalized_hash(prompt)
    logger.debug("Invalidating cache for %s", cid)
    _store.qa_cache.delete(ids=[cid])


def close_store() -> None:
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
    "qa_cache",
    "invalidate_cache",
    "close_store",
    "VectorStore",
    "MemoryVectorStore",
    "ChromaVectorStore",
]

