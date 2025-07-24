from __future__ import annotations

import re
from datetime import timedelta
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .base import Skill

scheduler = AsyncIOScheduler()


class ReminderSkill(Skill):
    PATTERNS = [re.compile(r"remind me to (.+) in (\d+) (seconds|minutes)", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        if not scheduler.running:
            scheduler.start()
        task = match.group(1)
        amount = int(match.group(2))
        unit = match.group(3)
        delay = amount * (60 if unit.startswith("minute") else 1)
        scheduler.add_job(lambda: None, "date", seconds=delay)
        return f"Reminder set for {task} in {amount} {unit}."
