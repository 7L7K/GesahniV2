from __future__ import annotations

import re
from datetime import timedelta

from .base import Skill
from .. import home_assistant as ha


class TimerSkill(Skill):
    PATTERNS = [
        re.compile(r"(?:start|set) a timer for (\d+) (seconds|minutes)", re.I),
        re.compile(r"timer for (\d+) (seconds|minutes)", re.I),
        re.compile(r"timer (\d+) (seconds|minutes)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        amount = int(match.group(1))
        unit = match.group(2).lower()
        total_seconds = amount * (60 if unit.startswith("minute") else 1)
        duration = str(timedelta(seconds=total_seconds))
        await ha.call_service(
            "timer",
            "start",
            {"entity_id": "timer.gesahni", "duration": duration},
        )
        return f"Timer started for {amount} {unit}."
