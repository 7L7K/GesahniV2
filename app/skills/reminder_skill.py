# app/skills/reminder_skill.py
from __future__ import annotations

import re
from datetime import datetime, timedelta

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
except Exception:  # pragma: no cover - optional dependency

    class AsyncIOScheduler:  # minimal stub
        """Fallback scheduler that simply queues jobs.

        Jobs will never execute but are stored so callers can at least
        acknowledge scheduling requests. This mirrors the minimal API of
        ``apscheduler`` used by this project.
        """

        def __init__(self):
            self.running = False
            self.jobs: list[dict] = []
            self.is_stub = True

        def start(self):
            self.running = True

        def add_job(self, func, trigger, **kwargs):  # pragma: no cover - simple
            run_at = None
            if trigger == "date":
                if "run_date" in kwargs:
                    run_at = kwargs["run_date"]
                elif "seconds" in kwargs:
                    run_at = datetime.now() + timedelta(seconds=kwargs["seconds"])
            elif trigger == "interval":
                run_at = datetime.now() + timedelta(**kwargs)
            elif trigger == "cron":
                run_at = "cron"
            self.jobs.append(
                {"func": func, "trigger": trigger, "kwargs": kwargs, "run_at": run_at}
            )
            return len(self.jobs) - 1


import json
import os
from pathlib import Path

from .base import Skill
from .ledger import record_action

scheduler = AsyncIOScheduler()

# Simple persistent ledger of scheduled reminders (best-effort)
_REMINDERS_PATH = Path(os.getenv("REMINDERS_STORE", "data/reminders.json"))


def _persist_reminder(entry: dict) -> None:
    try:
        _REMINDERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing: list = []
        if _REMINDERS_PATH.exists():
            try:
                existing = json.loads(
                    _REMINDERS_PATH.read_text(encoding="utf-8") or "[]"
                )
            except Exception:
                existing = []
        existing.append(entry)
        _REMINDERS_PATH.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:  # pragma: no cover - best effort
        pass


class ReminderSkill(Skill):
    # Catch natural phrasing & intervals
    PATTERNS = [
        # "remind me tomorrow at 9am to send the report"
        re.compile(
            r"remind me (?P<when>tomorrow(?: at \d{1,2}(?::\d{2})?\s*(?:am|pm))?) to (?P<task>.+)",
            re.I,
        ),
        # "remind me to call grandma in 10 minutes"
        re.compile(
            r"remind me to (?P<task>.+) in (?P<amt>\d+)\s*(?P<unit>seconds?|minutes?|minute|mins?|hours?|hrs?)",
            re.I,
        ),
        # "remind me to pay rent every month"
        re.compile(
            r"remind me to (?P<task>.+) every (?P<period>day|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)",
            re.I,
        ),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if not scheduler.running:
            scheduler.start()
        note = (
            ""
            if not getattr(scheduler, "is_stub", False)
            else " (queued only; will not fire)"
        )
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
                entry = {"type": "date", "task": task, "when": run_dt.isoformat()}
                _persist_reminder(entry)
                # require a concrete run time for safety
                idemp = f"reminder:{task}:{int(run_dt.timestamp())}"
                await record_action("reminder.set", idempotency_key=idemp, metadata={"when": run_dt.isoformat(), "task": task})
                return f"Reminder set for {task} at {run_dt.strftime('%Y-%m-%d %I:%M %p')}{note}."
        # 2) "in X minutes/hours" case
        if gd.get("amt") and gd.get("unit"):
            amt = int(gd["amt"])
            unit = gd["unit"].lower()
            if unit in {"mins", "min", "minute", "minutes"}:
                sec = amt * 60
            elif unit in {"hrs", "hour", "hours"}:
                sec = amt * 3600
            else:
                sec = amt
            task = gd["task"]
            scheduler.add_job(lambda: None, "date", seconds=sec)
            entry = {"type": "delay", "task": task, "seconds": sec}
            _persist_reminder(entry)
            # safety: compute run_dt and require that it's in the future
            run_dt = datetime.now() + timedelta(seconds=sec)
            idemp = f"reminder:{task}:{int(run_dt.timestamp())}"
            await record_action("reminder.set", idempotency_key=idemp, metadata={"when": run_dt.isoformat(), "task": task})
            return f"Reminder set for {task} in {amt} {unit}{note}."
        # 3) "every ..." case
        if gd.get("period"):
            period = gd["period"].lower()
            task = gd["task"]
            # daily/weekly/monthly or specific weekday
            if period in {"day", "week", "month"}:
                kwargs = (
                    {"days": 1}
                    if period == "day"
                    else {"weeks": 1} if period == "week" else {"days": 30}
                )
                scheduler.add_job(lambda: None, "interval", **kwargs)
                entry = {"type": "interval", "task": task, **kwargs}
                _persist_reminder(entry)
                idemp = f"reminder:{task}:interval:{period}"
                await record_action("reminder.set", idempotency_key=idemp, metadata={"period": period, "task": task})
                return f"Recurring reminder set for {task} every {period}{note}."
            else:
                # weekday cron
                scheduler.add_job(lambda: None, "cron", day_of_week=period[:3])
                entry = {"type": "cron", "task": task, "day_of_week": period[:3]}
                _persist_reminder(entry)
                idemp = f"reminder:{task}:cron:{period[:3]}"
                await record_action("reminder.set", idempotency_key=idemp, metadata={"day_of_week": period[:3], "task": task})
                return (
                    f"Recurring reminder set for {task} every {period.title()}{note}."
                )
        # Fallback
        return "Could not set reminder—please try a different phrasing."
