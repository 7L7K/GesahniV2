from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Optional, Pattern, List


class Skill(ABC):
    """Abstract base class for all built in skills."""

    PATTERNS: List[Pattern[str]] = []

    def match(self, prompt: str) -> Optional[re.Match]:
        for pat in self.PATTERNS:
            m = pat.search(prompt)
            if m:
                return m
        return None

    @abstractmethod
    async def run(self, prompt: str, match: re.Match) -> str:
        """Execute the skill and return the response text."""
        raise NotImplementedError


SKILLS: List[Skill] = []


async def check_builtin_skills(prompt: str) -> Optional[str]:
    """Return a response from the first matching skill or ``None``."""
    for skill in SKILLS:
        m = skill.match(prompt)
        if m:
            return await skill.run(prompt, m)
    return None
