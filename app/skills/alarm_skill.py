from __future__ import annotations

import re
from datetime import datetime, timedelta

from .base import Skill
from ..deps import scheduler as sched

scheduler = sched.scheduler
start_scheduler = sched.start


class AlarmSkill(Skill):
    """Set a one-shot alarm at a specific clock time."""

    PATTERNS = [
        re.compile(r"set an alarm for (?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm))", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        start_scheduler()
        timestr = match.group("time").lower()
        m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", timestr)
        if not m:
            return "Could not parse time."
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        ampm = m.group(3)
        if ampm == "pm" and hour < 12:
            hour += 12
        if ampm == "am" and hour == 12:
            hour = 0
        now = datetime.now()
        run_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if run_dt <= now:
            run_dt += timedelta(days=1)
        scheduler.add_job(lambda: None, "date", run_date=run_dt)
        return f"Alarm set for {run_dt.strftime('%I:%M %p').lstrip('0')}"
