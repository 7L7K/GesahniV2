from __future__ import annotations

import re
from pathlib import Path
from typing import List

from .base import Skill
from .ledger import record_action

_SUG_PATH = Path("data/suggestions.json")


def _load_suggestions() -> List[dict]:
    try:
        import json

        return json.loads(_SUG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_suggestions(lst: List[dict]) -> None:
    try:
        import json

        _SUG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _SUG_PATH.write_text(json.dumps(lst, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


class SuggestionsSkill(Skill):
    PATTERNS = [re.compile(r"show suggestions", re.I), re.compile(r"dismiss suggestion (?P<idx>\d+)", re.I)]

    async def run(self, prompt: str, match) -> str:
        gd = match.groupdict()
        if gd.get("idx"):
            idx = int(gd["idx"]) - 1
            s = _load_suggestions()
            if 0 <= idx < len(s):
                s.pop(idx)
                _save_suggestions(s)
                await record_action("suggestion.dismiss", idempotency_key=None, metadata={"idx": idx}, reversible=False)
                return "Suggestion dismissed."
            return "No such suggestion."
        s = _load_suggestions()
        if not s:
            return "No suggestions right now."
        # present as numbered queue with why
        out = []
        for i, it in enumerate(s, start=1):
            out.append(f"{i}. {it.get('text')} — why: {it.get('why', 'no reason')}")
        return "\n".join(out)


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


