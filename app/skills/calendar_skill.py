from __future__ import annotations

import json
import os
import re
from pathlib import Path
import datetime as _dt

from .base import Skill

CAL_FILE = Path(os.getenv("CALENDAR_FILE", "data/calendar.json"))


class CalendarSkill(Skill):
    PATTERNS = [
        re.compile(r"\btoday'?s (?:events|appointments)\b", re.I),
        re.compile(r"\bupcoming (?:events|appointments)\b", re.I),
        re.compile(r"\bwhat(?:'s| is)? on my calendar\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        try:
            with CAL_FILE.open() as f:
                events = json.load(f)
        except Exception:
            return "No calendar data available."

        today = _dt.date.today().isoformat()
        if "upcoming" in prompt.lower():
            items = [e for e in events if e.get("date", "") >= today]
        else:
            items = [e for e in events if e.get("date") == today]
        if not items:
            return "No events found."
        parts = []
        for e in items:
            time = e.get("time", "")
            title = e.get("title", "")
            if time:
                parts.append(f"{time} {title}")
            else:
                parts.append(title)
        return " | ".join(parts)
