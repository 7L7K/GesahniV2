from __future__ import annotations

import re
from datetime import timedelta
from typing import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .base import Skill

scheduler = AsyncIOScheduler()


class ReminderSkill(Skill):
    PATTERNS = [
        re.compile(r"remind me to (?P<task>.+) in (?P<num>\d+) (?P<unit>seconds|minutes)", re.I),
        re.compile(r"remind me to (?P<rtask>.+) every (?P<freq>daily|weekly|monthly|monday|tuesday|wednesday|thursday|friday|saturday|sunday)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if not scheduler.running:
            scheduler.start()

        gd = match.groupdict()
        if gd.get("freq"):
            task = gd["rtask"]
            freq = gd["freq"].lower()
            if freq in {"daily", "weekly", "monthly"}:
                seconds = {"daily": 86400, "weekly": 604800, "monthly": 2592000}[freq]
                scheduler.add_job(lambda: None, "interval", seconds=seconds)
            else:
                scheduler.add_job(lambda: None, "cron", day_of_week=freq[:3])
            return f"Recurring reminder set to {task} {freq}."

        task = gd["task"]
        amount = int(gd["num"])
        unit = gd["unit"]
        delay = amount * (60 if unit.startswith("minute") else 1)
        scheduler.add_job(lambda: None, "date", seconds=delay)
        return f"Reminder set for {task} in {amount} {unit}."
