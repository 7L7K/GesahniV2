from __future__ import annotations

import datetime as _dt
import re
from zoneinfo import ZoneInfo

from .base import Skill

# minimal city to timezone mapping
CITY_TZS = {
    "tokyo": "Asia/Tokyo",
    "london": "Europe/London",
    "new york": "America/New_York",
    "los angeles": "America/Los_Angeles",
    "sydney": "Australia/Sydney",
}


class WorldClockSkill(Skill):
    PATTERNS = [
        re.compile(r"\bwhat time is it in ([\w\s]+)\??", re.I),
        re.compile(r"\btime in ([\w\s]+)\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        city = match.group(1).strip().lower()
        tz_name = CITY_TZS.get(city)
        if not tz_name:
            return f"I don't know the timezone for {city.title()}."
        now = _dt.datetime.now(ZoneInfo(tz_name)).strftime("%H:%M")
        return f"It's {now} in {city.title()}."
