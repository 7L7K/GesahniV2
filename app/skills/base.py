from __future__ import annotations

import re
import unicodedata  # ← NEW
from abc import ABC, abstractmethod
from re import Pattern

from ..history import append_history
from ..telemetry import log_record_var


class Skill(ABC):
    """Abstract base class for all built in skills."""

    PATTERNS: list[Pattern[str]] = []

    # Optional short human-readable "why" string a skill can set when it runs.
    # This should be a brief explanation (string) for observability only and
    # must not contain sensitive data. It is written to the current
    # telemetry LogRecord via `log_record_var` when available.
    skill_why: str | None = None

    def match(self, prompt: str) -> re.Match | None:
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
        # run() returns a text response. Skills may set `self.skill_why` as a
        # short explanation which the router will log; don't alter return type.
        resp = await self.run(prompt, m)
        return resp


SKILLS: list[Skill] = []


# ---------- NEW helper ----------
def _normalize(text: str) -> str:
    """Replace curly quotes / fancy dashes and collapse whitespace.

    This makes regexes far more resilient to pasted Unicode and odd spacing.
    """
    text = unicodedata.normalize("NFKD", text)
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
        "…": "...",
        "\u00A0": " ",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # Collapse multiple spaces/tabs/newlines into single spaces
    text = " ".join(text.split())
    return text


# ---------------------------------


async def check_builtin_skills(prompt: str) -> str | None:
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
