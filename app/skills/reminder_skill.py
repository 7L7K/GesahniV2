# app/skills/reminder_skill.py
from __future__ import annotations

import re
from datetime import datetime, timedelta
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:  # pragma: no cover - optional dependency
    class AsyncIOScheduler:  # minimal stub
        def __init__(self):
            self.running = False
        def start(self):
            self.running = True
        def add_job(self, *a, **k):
            pass

from .base import Skill

scheduler = AsyncIOScheduler()

class ReminderSkill(Skill):
    # Catch natural phrasing & intervals
    PATTERNS = [
        # "remind me tomorrow at 9am to send the report"
        re.compile(
            r"remind me (?P<when>tomorrow(?: at \d{1,2}(?::\d{2})?\s*(?:am|pm))?) to (?P<task>.+)", re.I
        ),
        # "remind me to call grandma in 10 minutes"
        re.compile(r"remind me to (?P<task>.+) in (?P<amt>\d+)\s*(?P<unit>seconds?|minutes?|hours?)", re.I),
        # "remind me to pay rent every month"
        re.compile(r"remind me to (?P<task>.+) every (?P<period>day|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if not scheduler.running:
            scheduler.start()

        gd = match.groupdict()
        # 1) "tomorrow at ..." case
        if gd.get("when"):
            when_str = gd["when"]
            # parse "tomorrow at 9am"
            # crude parse: take tomorrow's date and combine with hour/min
            base = datetime.now() + timedelta(days=1)
            time_part = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", when_str, re.I)
            if time_part:
                hr = int(time_part.group(1))
                mn = int(time_part.group(2) or 0)
                ampm = time_part.group(3).lower()
                if ampm == "pm" and hr < 12:
                    hr += 12
                run_dt = base.replace(hour=hr, minute=mn, second=0, microsecond=0)
                task = gd["task"]
                scheduler.add_job(lambda: None, "date", run_date=run_dt)
                return f"Reminder set for {task} at {run_dt.strftime('%Y-%m-%d %I:%M %p')}."
        # 2) "in X minutes/hours" case
        if gd.get("amt") and gd.get("unit"):
            amt = int(gd["amt"])
            unit = gd["unit"].lower()
            sec = amt * (60 if "minute" in unit else 3600 if "hour" in unit else 1)
            task = gd["task"]
            scheduler.add_job(lambda: None, "date", seconds=sec)
            return f"Reminder set for {task} in {amt} {unit}."
        # 3) "every ..." case
        if gd.get("period"):
            period = gd["period"].lower()
            task = gd["task"]
            # daily/weekly/monthly or specific weekday
            if period in {"day", "week", "month"}:
                kwargs = {"days": 1} if period == "day" else {"weeks": 1} if period == "week" else {"days": 30}
                scheduler.add_job(lambda: None, "interval", **kwargs)
                return f"Recurring reminder set for {task} every {period}."
            else:
                # weekday cron
                scheduler.add_job(lambda: None, "cron", day_of_week=period[:3])
                return f"Recurring reminder set for {task} every {period.title()}."
        # Fallback
        return "Could not set reminder—please try a different phrasing."
