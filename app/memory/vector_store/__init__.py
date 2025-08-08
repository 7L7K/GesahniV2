"""Compatibility wrapper re-exporting vector store API."""

"""Compatibility wrapper re-exporting vector store API.

The test-suite historically imported a number of helper functions directly from
``app.memory.vector_store``.  The project later refactored the code so that the
implementation lives in :mod:`app.memory.api` and :mod:`app.embeddings`, but the
tests (and potentially downstream projects) still expect those legacy symbols to
be present.  Importing and re-exporting them here keeps the public contract
intact while allowing the implementation to live elsewhere.
"""

from ..api import (
    ChromaVectorStore,
    MemoryVectorStore,
    VectorStore,
    add_user_memory,
    _get_store,
    cache_answer,
    cache_answer_legacy,
    close_store,
    invalidate_cache,
    lookup_cached_answer,
    qa_cache,
    query_user_memories,
    record_feedback,
)
from ..env_utils import _normalize, _normalized_hash
from app.embeddings import embed_sync

# Some legacy tests reach for ``_qa_cache`` directly.  Provide a thin alias so
# those imports continue to work even though the underlying store is now
# encapsulated by ``qa_cache``.
_qa_cache = qa_cache

__all__ = [
    "add_user_memory",
    "query_user_memories",
    "cache_answer",
    "cache_answer_legacy",
    "lookup_cached_answer",
    "record_feedback",
    "qa_cache",
    "_qa_cache",
    "_get_store",
    "invalidate_cache",
    "close_store",
    "VectorStore",
    "MemoryVectorStore",
    "ChromaVectorStore",
    "embed_sync",
    "_normalize",
    "_normalized_hash",
]

