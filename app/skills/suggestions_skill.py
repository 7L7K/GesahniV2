from __future__ import annotations

import re
from typing import Any, Dict, List

from .base import Skill

# Simple in-memory suggestion queue for demo purposes
_SUGGESTIONS: List[Dict[str, Any]] = []


class SuggestionsSkill(Skill):
    PATTERNS = [re.compile(r"show suggestions", re.I), re.compile(r"accept suggestion (?P<id>\d+)", re.I), re.compile(r"dismiss suggestion (?P<id>\d+)", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("show"):
            if not _SUGGESTIONS:
                return "No suggestions right now."
            return "; ".join(f"{i}. {s.get('proposal')}" for i, s in enumerate(_SUGGESTIONS, 1))
        if match.re.pattern.startswith("accept"):
            idx = int(match.group("id")) - 1
            if 0 <= idx < len(_SUGGESTIONS):
                s = _SUGGESTIONS.pop(idx)
                return f"Accepted suggestion: {s.get('proposal')}"
            return "Suggestion not found."
        if match.re.pattern.startswith("dismiss"):
            idx = int(match.group("id")) - 1
            if 0 <= idx < len(_SUGGESTIONS):
                s = _SUGGESTIONS.pop(idx)
                return f"Dismissed suggestion: {s.get('proposal')}"
            return "Suggestion not found."
        return "Could not parse suggestion command."

    # Helper for learners to push suggestions
    @staticmethod
    def push_suggestion(sugg: Dict[str, Any]) -> None:
        _SUGGESTIONS.append(sugg)

__all__ = ["SuggestionsSkill"]


