"""Compatibility wrapper re‑exporting vector‑store API.

This package‑level ``__init__`` gives tests and call‑sites a single import path
(``app.memory.vector_store``) while hardening *all* RAG look‑ups so a bad ``k``
value can’t sneak through and blow up the real store implementation.
"""

from __future__ import annotations

import logging
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
    _get_sim_threshold as _get_sim_threshold,
    _cosine_similarity as _cosine_similarity,
    _normalize as _normalize,
    _normalized_hash as _normalized_hash,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public re‑exports
# ---------------------------------------------------------------------------

# Surface the sync embed helper so callers aren’t coupled to the embeddings
# package’s private layout.
embed_sync = _embed_sync  # noqa: N816 (keep camelCase to match original API)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_k(k: Union[int, str, None]) -> int:
    """Return a sane positive ``int`` for ``k``.

    Rules:
    * ``None`` → project‑wide default via :func:`_get_mem_top_k`.
    * Strings are cast with ``int()``; failures or non‑positive results fall
      back to the default.
    * Any other non‑int type also falls back.
    """

    raw = k
    if k is None:
        result = _get_mem_top_k()
    else:
        try:
            value = int(k)  # handles str as well as float‑like ints
        except (TypeError, ValueError):
            result = _get_mem_top_k()
        else:
            result = value if value > 0 else _get_mem_top_k()

    logger.debug("_coerce_k: raw=%r → %d", raw, result)
    return result


def _get_cutoff() -> float:
    """Return the distance cutoff derived from similarity threshold."""

    return 1.0 - _get_sim_threshold()


def _distance(prompt: str, memory: str) -> float:
    """Return cosine distance between ``prompt`` and ``memory``."""

    return 1.0 - _cosine_similarity(embed_sync(prompt), embed_sync(memory))


# ---------------------------------------------------------------------------
# Safer API surface
# ---------------------------------------------------------------------------


def query_user_memories(
    user_id: str,
    prompt: str,
    *,
    k: Union[int, str, None] = None,
) -> List[str]:
    """Vector‑store RAG lookup with bullet‑proof ``k`` handling."""
    safe_k = _coerce_k(k)
    cutoff = _get_cutoff()
    memories = _raw_query_user_memories(user_id, prompt, k=safe_k)
    return [m for m in memories if _distance(prompt, m) <= cutoff]


def safe_query_user_memories(
    user_id: str,
    prompt: str,
    *,
    k: Union[int, str, None] = None,
) -> List[str]:
    """Alias kept for backward compatibility (extra debug logging)."""

    logger.debug(
        "safe_query_user_memories(user_id=%s, prompt=%r, k=%r)",
        user_id,
        prompt,
        k,
    )
    memories = query_user_memories(user_id, prompt, k=k)
    logger.debug("→ returning %d memories", len(memories))
    return memories


# ---------------------------------------------------------------------------
# What we expose to the rest of the codebase
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

# Provide `_get_store` for tests that reach in (but keep it out of production
# code by convention).
try:  # pragma: no cover – test‑only import path
    from ..api import _get_store as _get_store  # type: ignore
except Exception:  # pragma: no cover – defensive
    _get_store = None
else:
    __all__.append("_get_store")
