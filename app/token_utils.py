"""Utilities for token counting."""

from __future__ import annotations

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
    return len(text.split())


__all__ = ["count_tokens"]
