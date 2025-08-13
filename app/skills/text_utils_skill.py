from __future__ import annotations

import re

from .base import Skill


class TextUtilsSkill(Skill):
    PATTERNS = [
        re.compile(r"^slugify:\s*(?P<text>.+)$", re.I),
        re.compile(r"^word count:\s*(?P<text>.+)$", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if prompt.lower().startswith("slugify:"):
            text = match.group("text")
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            return slug
        text = match.group("text")
        words = len([w for w in re.split(r"\s+", text.strip()) if w])
        return str(words)


