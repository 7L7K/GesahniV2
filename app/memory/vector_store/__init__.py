"""Compatibility wrapper re‑exporting vector‑store API.

This package‑level ``__init__`` gives tests and call‑sites a single import path
(``app.memory.vector_store``) while hardening *all* RAG look‑ups so a bad ``k``
value can’t sneak through and blow up the real store implementation.
"""

from __future__ import annotations

import logging
import re
from typing import List, Union

from ..api import (
    ChromaVectorStore,
    MemoryVectorStore,
    VectorStore,
    cache_answer,
    cache_answer_legacy,
    close_store,
    invalidate_cache,
    lookup_cached_answer,
    qa_cache,
    record_feedback,
)
from app.adapters.memory import mem
from app.embeddings import embed_sync as _embed_sync
from ..memory_store import _get_last_similarity as _get_last_similarity  # type: ignore
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


def add_user_memory(user_id: str, memory: str) -> str:
    """Persist a single memory via the configured backend."""

    return mem.add(user_id, memory)


def query_user_memories(
    user_id: str,
    prompt: str,
    *,
    k: Union[int, str, None] = None,
    filters: dict | None = None,
) -> List[str]:
    """Vector‑store RAG lookup with tolerant ``k`` handling.

    Only coerce numeric strings → int; otherwise let the underlying API apply
    its own defaults so tests can control the default via monkeypatch.
    """
    if isinstance(k, str):
        try:
            k_arg = int(k)
        except ValueError:
            k_arg = None
    else:
        k_arg = k

    k_int = _coerce_k(k_arg)
    docs = mem.search(user_id, prompt, k=k_int, filters=filters)
    cutoff = _get_cutoff()
    out: List[str] = []
    for d in docs:
        text = d.get("text") if isinstance(d, dict) else str(d)
        if _distance(prompt, text) <= cutoff:
            out.append(text)
    return out


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
    # Coerce only numeric strings; invalid strings pass through as None
    coerced: Union[int, None, str]
    if isinstance(k, str):
        try:
            coerced = int(k)
        except ValueError:
            coerced = None
    else:
        coerced = k

    filters: dict[str, str] = {}
    person = re.search(r"person:([^\s]+)", prompt)
    topic = re.search(r"topic:([^\s]+)", prompt)
    date = re.search(r"date:([^\s]+)", prompt)
    if person:
        filters["person"] = person.group(1)
    if topic:
        filters["topic"] = topic.group(1)
    if date:
        filters["date"] = date.group(1)

    memories: List[str] = []
    try:
        if filters:
            memories = query_user_memories(user_id, "", k=coerced, filters=filters)
        if not memories:
            memories = query_user_memories(user_id, prompt, k=coerced)
    except Exception as e:  # pragma: no cover - defensive guardrail
        # Never allow RAG lookup failures to break routing; degrade gracefully.
        logger.warning("safe_query_user_memories failed: %s", e, exc_info=True)
        memories = []
    logger.debug("→ returning %d memories", len(memories))
    return memories


# Expose last similarity when using MemoryVectorStore for UI debugging
try:
    from ..memory_store import _get_last_similarity as get_last_cache_similarity  # type: ignore
except Exception:  # pragma: no cover - fallback
    def get_last_cache_similarity() -> float | None:  # type: ignore
        return None


def get_last_cache_similarity() -> float | None:
    """Return similarity score of the most recent QA cache hit (if available)."""

    try:
        return _get_last_similarity()
    except Exception:
        return None


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
    "get_last_cache_similarity",
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
