"""Utilities for token counting."""

from __future__ import annotations

import math

try:  # pragma: no cover - optional dependency
    import tiktoken

    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover - simple fallback
    _ENCODING = None  # type: ignore


def count_tokens(text: str) -> int:
    """Return the number of tokens in ``text``.

    Uses ``tiktoken`` when available; otherwise falls back to a naive
    whitespace-based count.  This mirrors the historical logic that lived in
    ``prompt_builder``.
    """

    if _ENCODING is not None:
        return len(_ENCODING.encode(text))
    # Fallback heuristic: approximate tokens for both spaced and unspaced text
    if not text:
        return 0
    # If there are spaces, use word count with a multiplier
    if any(ch.isspace() for ch in text):
        words = len(text.split())
        # Roughly 0.75 tokens per short English word; bound to at least words
        return max(words, int(math.ceil(words * 0.75)))
    # No spaces (e.g., long loremipsum) — assume ~4 chars/token
    return int(math.ceil(len(text) / 4.0))


__all__ = ["count_tokens"]
