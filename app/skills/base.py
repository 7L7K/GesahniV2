from __future__ import annotations

import re
import unicodedata          # ← NEW
from abc import ABC, abstractmethod
from typing import Optional, Pattern, List

from ..history import append_history
from ..telemetry import log_record_var


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

    async def handle(self, prompt: str) -> str:
        """Convenience wrapper used by the router."""
        m = self.match(prompt)
        if not m:
            raise ValueError("no pattern matched")
        return await self.run(prompt, m)


SKILLS: List[Skill] = []


# ---------- NEW helper ----------
def _normalize(text: str) -> str:
    """Replace curly quotes / fancy dashes with ASCII equivalents."""
    text = unicodedata.normalize("NFKD", text)
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text
# ---------------------------------


async def check_builtin_skills(prompt: str) -> Optional[str]:
    """Return a response from the first matching skill or ``None``.

    Any matched skill response is also logged to the history file using the
    skill class name as ``engine_used``.
    """
    norm = _normalize(prompt)  # use normalized text for matching
    for skill in SKILLS:
        m = skill.match(norm)
        if m:
            resp = await skill.run(prompt, m)
            rec = log_record_var.get()
            if rec is not None:
                rec.matched_skill = skill.__class__.__name__
                rec.match_confidence = 1.0
                rec.engine_used = skill.__class__.__name__
                rec.response = str(resp)
            await append_history(prompt, skill.__class__.__name__, str(resp))
            return resp
    return None
