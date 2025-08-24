from __future__ import annotations

import os

from .token_utils import count_tokens


def _table(intent: str | None) -> tuple[int, int]:
    """Return (max_in, max_out) token caps for a given intent.

    Defaults may be overridden via env like INTENT_CAP_chat_IN, INTENT_CAP_chat_OUT.
    """

    base = {
        "smalltalk": (200, 400),
        "chat": (800, 800),
        "recall_story": (300, 600),
        "search": (600, 800),
        "code": (1000, 1200),
    }
    key = (intent or "chat").lower()
    max_in, max_out = base.get(key, base["chat"])  # type: ignore[index]
    ei = os.getenv(f"INTENT_CAP_{key}_IN")
    eo = os.getenv(f"INTENT_CAP_{key}_OUT")
    if ei and ei.isdigit():
        max_in = int(ei)
    if eo and eo.isdigit():
        max_out = int(eo)
    return max_in, max_out


def clamp_prompt(prompt: str, intent: str | None, max_tokens: int | None = None) -> str:
    """Truncate the user prompt when it exceeds the per-intent cap.

    A simple heuristic based on token count with a conservative character fallback.
    """

    # Use provided max_tokens if given, otherwise get from intent table
    if max_tokens is not None:
        max_in = max_tokens
    else:
        max_in, _ = _table(intent)

    if max_in <= 0:
        return prompt
    t = count_tokens(prompt)
    if t <= max_in:
        return prompt
    # Conservatively trim by characters using a 4 chars/token heuristic
    approx_chars = max_in * 4
    trimmed = prompt[:approx_chars]
    # Ensure we don't cut mid-word too harshly
    last_space = trimmed.rfind(" ")
    if last_space > 40:
        trimmed = trimmed[:last_space]
    return trimmed + "\n\n[truncated]"


__all__ = ["clamp_prompt", "_table"]
