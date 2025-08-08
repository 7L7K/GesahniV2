"""High level vector store API used throughout the project."""

from __future__ import annotations

import logging
import os
import sys
from typing import List, Optional

from app.telemetry import hash_user_id

from .chroma_store import ChromaVectorStore
from .env_utils import _get_mem_top_k, _normalized_hash
from .memory_store import MemoryVectorStore, VectorStore


logger = logging.getLogger(__name__)


def _get_store() -> VectorStore:
    """Return the configured vector store backend."""

    kind = os.getenv("VECTOR_STORE", "").lower()
    chroma_path = os.getenv("CHROMA_PATH", ".chroma_data")
    if (
        kind in ("memory", "inmemory")
        or "PYTEST_CURRENT_TEST" in os.environ
        or "pytest" in sys.modules
    ):
        logger.info("Using MemoryVectorStore (test mode or VECTOR_STORE=%s)", kind)
        store: VectorStore = MemoryVectorStore()
    else:
        try:
            if not chroma_path:
                raise FileNotFoundError("CHROMA_PATH is empty")
            logger.info("Initializing ChromaVectorStore at path: %s", chroma_path)
            store = ChromaVectorStore()
        except Exception as exc:
            if os.getenv("ENV", "").lower() == "production":
                logger.error("FATAL: ChromaVectorStore failed in production: %s", exc)
                raise
            logger.warning(
                "ChromaVectorStore unavailable at %s: %s; falling back to MemoryVectorStore",
                chroma_path,
                exc,
            )
            store = MemoryVectorStore()
    logger.debug("Vector store backend selected: %s", type(store).__name__)
    return store


_store: VectorStore = _get_store()


def add_user_memory(user_id: str, memory: str) -> str:
    return _store.add_user_memory(user_id, memory)


def _coerce_k(k: int | str | None) -> int:
    """Return a positive integer ``k`` with a sensible default."""

    if k is None:
        result = _get_mem_top_k()
    else:
        try:
            value = int(k)
        except (TypeError, ValueError):
            result = _get_mem_top_k()
        else:
            result = value if value > 0 else _get_mem_top_k()
    logger.debug("Coerced k=%r -> %d", k, result)
    return result


def query_user_memories(
    user_id: str, prompt: str, k: int | str | None = None
) -> List[str]:
    k_int = _coerce_k(k)
    logger.debug(
        "query_user_memories args: user=%s prompt=%r k=%d",
        hash_user_id(user_id),
        prompt,
        k_int,
    )
    res = _store.query_user_memories(user_id, prompt, k_int)
    logger.debug("query_user_memories returned %d items", len(res))
    return res


def cache_answer(prompt: str, answer: str, cache_id: str | None = None) -> None:
    """Cache an answer for the given prompt.

    Parameters
    ----------
    prompt:
        Normalized prompt text.
    answer:
        Response text to cache.
    cache_id:
        Optional explicit cache identifier. If omitted the identifier is
        generated from a normalized hash of the prompt.
    """

    cid = cache_id or _normalized_hash(prompt)
    _store.cache_answer(cid, prompt, answer)


def cache_answer_legacy(*args) -> None:  # pragma: no cover - shim for callers
    """Backward compatible wrapper for positional cache_answer usage.

    This helper emits a ``DeprecationWarning`` and forwards to
    :func:`cache_answer` using the new explicit signature. It will be removed
    once all callers are migrated.
    """

    import warnings

    warnings.warn(
        "cache_answer positional arguments are deprecated; use "
        "cache_answer(prompt, answer, cache_id=None)",
        DeprecationWarning,
        stacklevel=2,
    )

    if len(args) == 2:
        cache_answer(args[0], args[1])
    elif len(args) == 3:
        cache_answer(args[1], args[2], cache_id=args[0])
    else:
        raise TypeError("cache_answer_legacy expects 2 or 3 arguments")


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
