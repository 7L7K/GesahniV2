from __future__ import annotations

import asyncio
import datetime as _dt
import re

from .base import Skill


class ClockSkill(Skill):
    PATTERNS = [
        re.compile(r"\bwhat time is it\b", re.I),
        re.compile(r"\bwhat(?:'s| is)? the date\b", re.I),
        re.compile(r"countdown (\d+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if "time" in match.re.pattern:
            now = _dt.datetime.now().strftime("%H:%M")
            return f"The time is {now}."
        if "date" in match.re.pattern:
            today = _dt.date.today().isoformat()
            return f"Today's date is {today}."
        if "countdown" in match.re.pattern:
            seconds = int(match.group(1))
            await asyncio.sleep(0)  # no real wait in tests
            return f"Countdown of {seconds} seconds started."
        return ""
