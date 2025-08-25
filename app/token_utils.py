from __future__ import annotations
"""Utilities for token counting."""


import math

try:  # pragma: no cover - optional dependency
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - simple fallback
    _ENCODING = None  # type: ignore


def count_tokens(text: str) -> int:
    """Return the number of tokens in ``text``.

    - Uses ``tiktoken`` when available but never undercounts relative to a
      stable heuristic for no‑space strings (≈4 chars per token).
    - For spaced text, prefer tiktoken when present; else approximate by words.
    """

    if not text:
        return 0

    has_space = any(ch.isspace() for ch in text)

    # Heuristic approximations used as floors to avoid undercounting
    if has_space:
        words = len(text.split())
        approx = max(words, int(math.ceil(words * 0.75)))
    else:
        approx = int(math.ceil(len(text) / 4.0))

    if _ENCODING is not None:
        try:
            real = len(_ENCODING.encode(text))
            # Never report fewer than our approximation, especially for no‑space text
            return max(real, approx)
        except Exception:
            return approx

    return approx


__all__ = ["count_tokens"]
