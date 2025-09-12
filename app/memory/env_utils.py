from __future__ import annotations

"""Utility helpers for vector store modules."""


import hashlib
import logging
import os
import unicodedata
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def _env_flag(name: str) -> bool:
    """Return True if an environment variable is truthy."""

    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


DEFAULT_SIM_THRESHOLD = 0.24

DEFAULT_MEM_TOP_K = 3


def _get_sim_threshold() -> float:
    """Read the similarity threshold from the ``SIM_THRESHOLD`` env var."""

    raw = os.getenv("SIM_THRESHOLD", str(DEFAULT_SIM_THRESHOLD))
    try:
        value = float(raw)
    except ValueError:  # pragma: no cover - defensive
        logger.warning(
            "Invalid SIM_THRESHOLD %r; falling back to %.2f",
            raw,
            DEFAULT_SIM_THRESHOLD,
        )
        return DEFAULT_SIM_THRESHOLD
    if not 0.0 <= value <= 1.0:
        clamped = min(max(value, 0.0), 1.0)
        logger.warning(
            "SIM_THRESHOLD %.2f out of range [0, 1]; clamped to %.2f",
            value,
            clamped,
        )
        return clamped
    return value


def _get_mem_top_k() -> int:
    """Read the ``MEM_TOP_K`` env var with sane bounds."""

    raw = os.getenv("MEM_TOP_K", str(DEFAULT_MEM_TOP_K))
    try:
        value = int(raw)
    except ValueError:  # pragma: no cover - defensive
        logger.warning(
            "Invalid MEM_TOP_K %r; falling back to %d",
            raw,
            DEFAULT_MEM_TOP_K,
        )
        return DEFAULT_MEM_TOP_K
    if value < 1 or value > 10:
        clamped = min(max(value, 1), 10)
        logger.warning(
            "MEM_TOP_K %d out of range [1, 10]; clamped to %d",
            value,
            clamped,
        )
        return clamped
    return value


def _clean_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Replace ``None`` metadata values with empty strings."""

    return {k: (v if v is not None else "") for k, v in meta.items()}


def _normalize(text: str) -> tuple[str, str]:
    """Return a stable hash and normalized text."""

    norm = unicodedata.normalize("NFKD", text)
    for bad, good in {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
    }.items():
        norm = norm.replace(bad, good)
    norm = " ".join(norm.split()).lower()
    h = hashlib.sha256(norm.encode()).hexdigest()
    return h, norm


def _normalized_hash(prompt: str) -> str:
    return _normalize(prompt)[0]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Return cosine similarity in [0, 1] for two vectors.

    The raw cosine ranges in [-1, 1]. We map to [0, 1] using (cos + 1) / 2
    and clamp to guard against floating point drift.
    """

    a_arr, b_arr = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
    if not denom:
        return 0.0
    raw = float(np.dot(a_arr, b_arr) / denom)
    sim = (raw + 1.0) / 2.0
    if sim < 0.0:
        return 0.0
    if sim > 1.0:
        return 1.0
    return sim


__all__ = [
    "_env_flag",
    "DEFAULT_SIM_THRESHOLD",
    "_get_sim_threshold",
    "DEFAULT_MEM_TOP_K",
    "_get_mem_top_k",
    "_clean_meta",
    "_normalize",
    "_normalized_hash",
    "_cosine_similarity",
]
