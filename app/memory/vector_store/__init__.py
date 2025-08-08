"""Compatibility wrapper re-exporting vector store API.

This module centralizes vector-store helpers under a single import path.
Tests rely on these re-exports to avoid pulling in heavy dependencies and
they provide a seam for swapping out the underlying provider in the future
without touching call sites.
"""

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

# Public re-export of sync embed helper so callers can stay decoupled from
# the embeddings module’s layout.
embed_sync = _embed_sync

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
    "_normalize",
    "_normalized_hash",
    "embed_sync",
]

# Re-export internal helper for tests that import module._get_store.
# Only add to ``__all__`` when the import succeeds.
try:  # pragma: no cover – test-only import path
    from ..api import _get_store as _get_store  # type: ignore
except Exception:  # pragma: no cover – defensive
    _get_store = None
else:
    __all__.append("_get_store")
