from __future__ import annotations

import random
import re
import string

from .base import Skill


_SAFE_CHARS = (
    string.ascii_letters
    + string.digits
    + "!@#$%^&*()_+-=[]{};:,.?"  # avoid quotes and backslashes to keep copy/paste safe
)


class PasswordSkill(Skill):
    PATTERNS = [
        # capture 1-3 digits to allow 100 and clamp later
        re.compile(r"\b(?:make|generate|create) (?:a )?(?:strong )?password(?: (\d{1,3}))?\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        length_str = match.group(1) if match.lastindex else None
        try:
            length = int(length_str) if length_str else 16
        except Exception:
            length = 16
        length = max(8, min(64, length))
        rng = random.SystemRandom()
        password = "".join(rng.choice(_SAFE_CHARS) for _ in range(length))
        return password


