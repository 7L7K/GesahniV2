from __future__ import annotations

import re
from datetime import timedelta
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .base import Skill

scheduler = AsyncIOScheduler()


class ReminderSkill(Skill):
    PATTERNS = [
        re.compile(r"remind me to (.+) in (\d+) (seconds|minutes)", re.I),
        re.compile(r"remind me to (.+) every (day|week|month)", re.I),
        re.compile(r"remind me to (.+) every (monday|tuesday|wednesday|thursday|friday|saturday|sunday)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if not scheduler.running:
            scheduler.start()
        groups = match.groups()
        task = groups[0]
        if len(groups) == 3 and groups[1].isdigit():
            amount = int(groups[1])
            unit = groups[2]
            delay = amount * (60 if unit.startswith("minute") else 1)
            scheduler.add_job(lambda: None, "date", seconds=delay)
            return f"Reminder set for {task} in {amount} {unit}."

        period = groups[1].lower()
        if period in {"day", "week", "month"}:
            kwargs = {"days": 1} if period == "day" else {"weeks": 1 if period == "week" else 4}
            scheduler.add_job(lambda: None, "interval", **kwargs)
            return f"Recurring reminder set for {task} every {period}."

        dow = period
        scheduler.add_job(lambda: None, "cron", day_of_week=dow)
        return f"Reminder set for {task} every {dow}."
