from __future__ import annotations

import re
from collections.abc import Iterable

DENY_LIST = [
    r"\bdelete\s+all\b",
    r"\bformat\s+drive\b",
    r"\bshutdown\b",
    r"\bmake\s+purchase\b",
]


def moderation_precheck(
    text: str, *, extra_phrases: Iterable[str] | None = None
) -> bool:
    """Return True if text passes a deny-list moderation pre-check.

    This is a conservative, local check intended to guard model-generated
    actions (e.g., HA service calls) before execution.
    """

    if not text:
        return True
    phrases = list(extra_phrases or [])
    for pat in DENY_LIST + [re.escape(p) for p in phrases if p]:
        if re.search(pat, text, re.I):
            return False
    return True


__all__ = ["moderation_precheck"]
