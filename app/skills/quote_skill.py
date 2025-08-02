from __future__ import annotations

import random
import re
from .base import Skill

QUOTES = [
    "The only way to do great work is to love what you do. – Steve Jobs",
    "Whether you think you can or you think you can't, you're right. – Henry Ford",
    "The harder you work for something, the greater you'll feel when you achieve it.",
]


class QuoteSkill(Skill):
    PATTERNS = [re.compile(r"\bquote\b", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        return random.choice(QUOTES)
