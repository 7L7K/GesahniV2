from __future__ import annotations

import re
import uuid

from .base import Skill


class UUIDSkill(Skill):
    PATTERNS = [
        re.compile(r"\b(?:make|generate|new) uuid(?: v(4|5))?\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        v = match.group(1) if match.lastindex else None
        if v == "5":
            return str(uuid.uuid5(uuid.NAMESPACE_URL, str(uuid.uuid4())))
        # default v4
        return str(uuid.uuid4())
