from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from .base import Skill
from .reminder_skill import scheduler

_ALARMS_PATH = Path(os.getenv("ALARMS_STORE", "data/alarms.json"))
ALARMS: Dict[str, str] = {}

if _ALARMS_PATH.exists():
    try:
        data = json.loads(_ALARMS_PATH.read_text(encoding="utf-8") or "{}")
        if isinstance(data, dict):
            ALARMS.update({str(k): str(v) for k, v in data.items()})
    except Exception:
        pass


def _persist_alarms() -> None:
    try:
        _ALARMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ALARMS_PATH.write_text(
            json.dumps(ALARMS, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


def _parse_time(t: str) -> datetime | None:
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", t, re.I)
    if not m:
        return None
    hr = int(m.group(1))
    mn = int(m.group(2) or 0)
    ampm = m.group(3).lower()
    if ampm == "pm" and hr < 12:
        hr += 12
    if ampm == "am" and hr == 12:
        hr = 0
    now = datetime.now()
    run_dt = now.replace(hour=hr, minute=mn, second=0, microsecond=0)
    if run_dt <= now:
        run_dt += timedelta(days=1)
    return run_dt


class AlarmSkill(Skill):
    PATTERNS = [
        re.compile(r"set alarm for (?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm))", re.I),
        re.compile(
            r"cancel alarm(?: for (?P<ctime>\d{1,2}(?::\d{2})?\s*(?:am|pm)))", re.I
        ),
        re.compile(r"(?:list|show) alarms", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if not scheduler.running:
            scheduler.start()
        gd = match.groupdict()

        if gd.get("time"):
            run_dt = _parse_time(gd["time"])  # type: ignore[arg-type]
            if not run_dt:
                return "Could not parse time."
            time_str = run_dt.strftime("%I:%M %p")
            job = scheduler.add_job(lambda: None, "date", run_date=run_dt)
            job_id = getattr(job, "id", str(job))
            ALARMS[time_str] = str(job_id)
            _persist_alarms()
            return f"Alarm set for {time_str}."

        if gd.get("ctime"):
            run_dt = _parse_time(gd["ctime"])  # type: ignore[arg-type]
            if not run_dt:
                return "Could not parse time."
            time_str = run_dt.strftime("%I:%M %p")
            job_id = ALARMS.pop(time_str, None)
            if not job_id:
                return "No such alarm."
            try:
                scheduler.remove_job(job_id)  # type: ignore[attr-defined]
            except Exception:
                pass
            _persist_alarms()
            return f"Alarm for {time_str} cancelled."

        if ALARMS:
            times = ", ".join(sorted(ALARMS.keys()))
            return f"Alarms set for {times}."
        return "No alarms set."
