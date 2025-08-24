from __future__ import annotations

import re
from datetime import datetime, timedelta

from .base import Skill
from .ledger import _inmem


class DaySummarySkill(Skill):
    PATTERNS = [re.compile(r"(today|yesterday|this week) summary", re.I), re.compile(r"summary (today|yesterday|week)", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        token = match.group(1) if match.groups() else "today"
        now = datetime.now()
        if token and token.lower().startswith("yest"):
            start = now - timedelta(days=1)
        elif token and token.lower().startswith("week"):
            start = now - timedelta(days=7)
        else:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # deterministic summary: count ledger entries since start
        try:
            entries = [e for e in _inmem if datetime.fromisoformat(e["ts"]) >= start]
        except Exception:
            entries = []
        counts = {}
        for e in entries:
            counts[e.get("action")] = counts.get(e.get("action"), 0) + 1

        if not counts:
            return "No events in the requested period."

        parts = [f"{k}: {v}" for k, v in counts.items()]
        return "; ".join(parts)

__all__ = ["DaySummarySkill"]


