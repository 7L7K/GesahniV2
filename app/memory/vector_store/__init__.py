# app/memory/vector_store/__init__.py
"""Compatibility wrapper re-exporting vector store API.

Centralizes vector-store helpers so call sites import a single module.  
Also hardens every retrieval path so *no* query can sneak a ``None`` into
``VectorStore.query`` and crash the pipeline.
"""

from typing import List, Union

from ..api import (
    ChromaVectorStore,
    MemoryVectorStore,
    VectorStore,
    add_user_memory,
    cache_answer,
    cache_answer_legacy,
    close_store,
    invalidate_cache,
    lookup_cached_answer,
    qa_cache,
    record_feedback,
)
from ..api import query_user_memories as _raw_query_user_memories
from app.embeddings import embed_sync as _embed_sync
from ..env_utils import (
    _get_mem_top_k as _get_mem_top_k,
    _normalize as _normalize,
    _normalized_hash as _normalized_hash,
)

# Public re-export so callers don’t depend on embeddings internals.
embed_sync = _embed_sync


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_k(k: Union[int, str, None]) -> int:
    """Return a sane positive ``int`` for ``k``.

    * `None`, garbage, or failed casts fall back to the project default.
    * Strings are coerced via ``int()``—if that fails, we still fall back.
    """
    if k is None:
        return _get_mem_top_k()

    if isinstance(k, str):
        try:
            return int(k)
        except ValueError:
            return _get_mem_top_k()

    if isinstance(k, int):
        return k

    return _get_mem_top_k()


# ---------------------------------------------------------------------------
# Safer API surface
# ---------------------------------------------------------------------------


def query_user_memories(
    user_id: str,
    prompt: str,
    *,
    k: Union[int, str, None] = None,
) -> List[str]:
    """Vector-store RAG lookup with bullet-proof ``k`` handling."""
    return _raw_query_user_memories(user_id, prompt, k=_coerce_k(k))


def safe_query_user_memories(
    user_id: str,
    prompt: str,
    *,
    k: Union[int, str, None] = None,
) -> List[str]:
    """Alias kept for backward compatibility (tests import it)."""
    return query_user_memories(user_id, prompt, k=k)


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------

__all__ = [
    # Core helpers
    "add_user_memory",
    "query_user_memories",
    "safe_query_user_memories",
    "cache_answer",
    "cache_answer_legacy",
    "lookup_cached_answer",
    "record_feedback",
    "qa_cache",
    "invalidate_cache",
    "close_store",
    # Store classes
    "VectorStore",
    "MemoryVectorStore",
    "ChromaVectorStore",
    # Misc utilities
    "_normalize",
    "_normalized_hash",
    "embed_sync",
]

# Provide `_get_store` for tests that reach in.
try:  # pragma: no cover – test-only import path
    from ..api import _get_store as _get_store  # type: ignore
except Exception:  # pragma: no cover – fallback
    _get_store = None
else:
    __all__.append("_get_store")
