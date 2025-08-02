from __future__ import annotations

import os
import re
from datetime import datetime

from .base import Skill
from .. import home_assistant as ha

CALENDAR_ENTITY = os.getenv("CALENDAR_ENTITY", "calendar.personal")


class CalendarSkill(Skill):
    """Fetch upcoming events from the default calendar."""

    PATTERNS = [
        re.compile(r"what(?:'s| is)? on my calendar(?: today)?(?: for the next (?P<num>\d+))?", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        num = int(match.group("num")) if match.groupdict().get("num") else 5
        now = datetime.utcnow()
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        path = f"/calendars/{CALENDAR_ENTITY}?start={now.isoformat()}&end={end.isoformat()}"
        try:
            events = await ha._request("GET", path)
        except Exception:
            return "Failed to fetch calendar events."
        if not events:
            return "No upcoming events."
        parts: list[str] = []
        for ev in events[:num]:
            title = ev.get("summary") or ev.get("title") or "Untitled"
            start = ev.get("start", {})
            if isinstance(start, dict):
                start_str = start.get("dateTime") or start.get("date")
            else:
                start_str = start
            time_str = ""
            if isinstance(start_str, str):
                try:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    time_str = dt.strftime("%I:%M %p").lstrip("0")
                except Exception:
                    time_str = start_str
            parts.append(f"{time_str} {title}".strip())
        return "; ".join(parts)
