from __future__ import annotations
# app/memory/vector_store/__init__.py
"""
Compatibility wrapper re-exporting vector-store API.

One stable import path for tests & call sites: `app.memory.vector_store`.
Keep this file SIDE-EFFECT FREE: no heavy imports or I/O at import time.
"""


import logging
import re
from typing import List, Union

from app.embeddings import embed_sync as _embed_sync

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
from ..env_utils import _cosine_similarity as _cosine_similarity
from ..env_utils import _get_mem_top_k as _get_mem_top_k
from ..env_utils import _get_sim_threshold as _get_sim_threshold
from ..env_utils import _normalize as _normalize
from ..env_utils import _normalized_hash as _normalized_hash

logger = logging.getLogger(__name__)

# Public re-export so callers aren’t coupled to embeddings’ internals
embed_sync = _embed_sync  # noqa: N816

# ------------------------- internal helpers -------------------------


def _coerce_k(k: int | str | None) -> int:
    raw = k
    if k is None:
        result = _get_mem_top_k()
    else:
        try:
            value = int(k)
        except (TypeError, ValueError):
            result = _get_mem_top_k()
        else:
            result = value if value > 0 else _get_mem_top_k()
    logger.debug("_coerce_k: raw=%r → %d", raw, result)
    return result


def _similarity(prompt: str, memory: str) -> float:
    return _cosine_similarity(embed_sync(prompt), embed_sync(memory))


# --------------------------- safe API layer --------------------------


def add_user_memory(user_id: str, memory: str) -> str:
    # Lazy import to avoid side-effects during pytest collection
    from app.adapters.memory import mem

    try:
        # Redact before storage and persist map out-of-band
        from app.redaction import redact_pii, store_redaction_map

        redacted, mapping = redact_pii(memory)
        mem_id = mem.add(user_id, redacted)
        try:
            store_redaction_map("user_memory", mem_id, mapping)
        except Exception:
            pass
        return mem_id
    except Exception:
        # Fallback to raw store if redaction utility is unavailable
        return mem.add(user_id, memory)


def query_user_memories(
    user_id: str,
    prompt: str,
    *,
    k: int | str | None = None,
    filters: dict | None = None,
) -> list[str]:
    # Lazy import keeps this module light
    from app.adapters.memory import mem

    k_int = _coerce_k(int(k) if isinstance(k, str) and k.isdigit() else k)
    docs = mem.search(user_id, prompt, k=k_int, filters=filters)
    sim_threshold = _get_sim_threshold()
    filtered: list[tuple[float, str]] = []
    total = 0
    for d in docs:
        text = d.get("text") if isinstance(d, dict) else str(d)
        total += 1
        sim = _similarity(prompt, text)
        if sim >= sim_threshold:
            filtered.append((sim, text))
    filtered.sort(key=lambda t: -t[0])
    out = [t for _, t in filtered[:k_int]]
    try:
        logger.info(
            "vector.query",
            extra={
                "meta": {
                    "backend": "adapter",
                    "sim_threshold": round(sim_threshold, 4),
                    "kept": len(out),
                    "total": total,
                }
            },
        )
    except Exception:
        pass
    return out


def safe_query_user_memories(
    user_id: str,
    prompt: str,
    *,
    k: int | str | None = None,
) -> list[str]:
    logger.debug(
        "safe_query_user_memories(user_id=%s, prompt=%r, k=%r)", user_id, prompt, k
    )
    coerced = None
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

    try:
        if filters:
            memories = query_user_memories(user_id, "", k=coerced, filters=filters)
            if memories:
                return memories
        return query_user_memories(user_id, prompt, k=coerced)
    except Exception as e:  # defensive degrade
        logger.warning("safe_query_user_memories failed: %s", e, exc_info=True)
        return []


def get_last_cache_similarity() -> float | None:
    # Lazy import avoids import-time coupling to memory_store
    try:
        from ..memory_store import _get_last_similarity  # type: ignore

        return _get_last_similarity()
    except Exception:
        return None


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

# Test-only convenience (lazy import to avoid hard coupling)
try:  # pragma: no cover
    from ..api import _get_store as _get_store  # type: ignore
except Exception:  # pragma: no cover
    _get_store = None
else:
    __all__.append("_get_store")
