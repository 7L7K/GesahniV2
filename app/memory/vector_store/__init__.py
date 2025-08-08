"""Compatibility wrapper re-exporting vector store API."""

from typing import List

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

embed_sync = _embed_sync


def _coerce_k(k: int | str | None) -> int | None:
    """Return ``k`` as an ``int`` when possible.

    A ``None`` or invalid value returns ``None`` so that callers may
    apply their own defaults.
    """

    if k is None:
        return None
    if isinstance(k, str):
        try:
            return int(k)
        except ValueError:
            return None
    return k


def safe_query_user_memories(
    user_id: str, prompt: str, *, k: int | str | None = None
) -> List[str]:
    """Wrapper around :func:`query_user_memories` that coerces ``k``.

    Parameters
    ----------
    user_id:
        The user identifier whose memories to query.
    prompt:
        The prompt text used to search memories.
    k:
        Desired number of memories to retrieve. Accepts ``int`` or ``str``
        values; invalid inputs fall back to ``None`` which triggers the
        default behaviour of :func:`query_user_memories`.
    """

    return query_user_memories(user_id, prompt, k=_coerce_k(k))


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

# Re-export internal helper for tests that import module._get_store
try:  # pragma: no cover - test-only import path
    from ..api import _get_store as _get_store  # type: ignore
except Exception:  # pragma: no cover - defensive
    pass
