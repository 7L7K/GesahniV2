from __future__ import annotations

import random
import re
import string
import uuid

from .base import Skill

_ALPHABET = string.ascii_letters + string.digits + "-_"


class IdSkill(Skill):
    PATTERNS = [
        re.compile(r"\bmake (?:an? )?id(?: (\d{1,2}))?\b", re.I),
        re.compile(r"\bnanoid(?: (\d{1,2}))?\b", re.I),
        re.compile(r"\buuid\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        p = prompt.lower()
        if "uuid" in p:
            return str(uuid.uuid4())
        # nanoid
        length = 21
        m = re.search(r"(\d{1,2})", prompt)
        if m:
            try:
                length = int(m.group(1))
            except Exception:
                length = 21
        length = max(4, min(64, length))
        rng = random.SystemRandom()
        return "".join(rng.choice(_ALPHABET) for _ in range(length))
