from __future__ import annotations

import random
import re

from .base import Skill


class FlashcardSkill(Skill):
    """Offer a quick Spanish vocabulary quiz."""

    PATTERNS = [
        re.compile(r"\b(?:flashcard|spanish vocab|spanish quiz)\b", re.I),
    ]

    DECK = [
        ("cat", "gato"),
        ("dog", "perro"),
        ("house", "casa"),
        ("water", "agua"),
        ("book", "libro"),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        eng, esp = random.choice(self.DECK)
        if random.random() < 0.5:
            return f"What is the Spanish word for '{eng}'?"
        return f"What does '{esp}' mean in English?"
