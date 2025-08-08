"""Compatibility wrapper re-exporting vector store API.

This module centralizes vector-store helpers under a single import path.
Tests rely on these re-exports to avoid heavy dependencies, and it keeps the
door open for swapping providers later without touching call sites.
"""

import logging
from typing import List, Optional, Union

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
    query_user_memories,
    record_feedback,
)
from app.embeddings import embed_sync as _embed_sync
from ..env_utils import _normalize as _normalize, _normalized_hash as _normalized_hash


logger = logging.getLogger(__name__)

# Public re-export of sync embed helper so callers stay decoupled from the
# embeddings module’s internal layout.
embed_sync = _embed_sync


# ---------------------------------------------------------------------------
# Safe wrapper helpers
# ---------------------------------------------------------------------------


def _coerce_k(k: Union[int, str, None]) -> Optional[int]:
    """Coerce ``k`` to ``int`` or return ``None`` when invalid."""

    if k is None:
        result: Optional[int] = None
    elif isinstance(k, str):
        try:
            result = int(k)
        except ValueError:
            result = None
    else:
        result = k if isinstance(k, int) else None
    logger.debug("Coerced k=%r -> %s", k, result)
    return result


def safe_query_user_memories(
    user_id: str, prompt: str, *, k: Union[int, str, None] = None
) -> List[str]:
    """Thin wrapper around :func:`query_user_memories` that sanitizes ``k``."""
    return query_user_memories(user_id, prompt, k=_coerce_k(k))


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------

__all__ = [
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
    "VectorStore",
    "MemoryVectorStore",
    "ChromaVectorStore",
    "_normalize",
    "_normalized_hash",
    "embed_sync",
]

# Re-export internal helper for tests that import module._get_store.
try:  # pragma: no cover – test-only import path
    from ..api import _get_store as _get_store  # type: ignore
except Exception:  # pragma: no cover – defensive
    _get_store = None
else:
    __all__.append("_get_store")
