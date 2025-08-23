from __future__ import annotations

import json
import os
import re
import time
from datetime import timedelta
from pathlib import Path

from .. import home_assistant as ha
from .base import Skill

TIMERS: dict[str, float] = {}
_TIMERS_STORE = Path(os.getenv("TIMERS_STORE", "data/timers.json"))


def _persist_timers() -> None:
    try:
        _TIMERS_STORE.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in TIMERS.items()}
        _TIMERS_STORE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:  # pragma: no cover - best effort
        pass


class TimerSkill(Skill):
    PATTERNS = [
        # "start/set <name?> timer for <n> <seconds|minutes>"
        re.compile(
            r"\b(?:start|set|begin|create) (?:(?P<name>[\w\-]+) )?timer for (?P<amount>\d+) (?P<unit>seconds?|minutes?|mins?)\b",
            re.I,
        ),
        # "pause/resume/cancel <name?> timer"
        re.compile(r"\b(?:pause|resume|cancel|stop) (?:(?P<cname>[\w\-]+) )?timer\b", re.I),
        # "how long left on <name?> timer"
        re.compile(r"\bhow (?:much |long )?left (?:on|for) (?:(?P<qname>[\w\-]+) )?timer\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        groups = match.groupdict()
        if "cname" in groups and groups["cname"] is not None:
            name = groups["cname"] or "gesahni"
            # extract first verb
            action = match.group(0).split()[0].lower()
            if action == "pause":
                await ha.call_service("timer", "pause", {"entity_id": f"timer.{name}"})
                return f"{name} timer paused."
            if action == "resume":
                await ha.call_service("timer", "start", {"entity_id": f"timer.{name}"})
                return f"{name} timer resumed."
            if action == "stop":
                await ha.call_service("timer", "cancel", {"entity_id": f"timer.{name}"})
                TIMERS.pop(name, None)
                _persist_timers()
                return f"{name} timer cancelled."
            await ha.call_service("timer", "cancel", {"entity_id": f"timer.{name}"})
            TIMERS.pop(name, None)
            _persist_timers()
            return f"{name} timer cancelled."

        if "qname" in groups and groups["qname"] is not None:
            name = groups["qname"] or "gesahni"
            if name not in TIMERS:
                return "No such timer."
            remaining = int(TIMERS[name] - time.monotonic())
            return f"{max(0, remaining)} seconds left on {name} timer."

        name = groups.get("name") or "gesahni"
        amount = int(groups["amount"])
        unit = groups["unit"].lower()
        if unit == "mins":
            unit = "minutes"
        total_seconds = amount * (60 if unit.startswith("minute") else 1)
        duration = str(timedelta(seconds=total_seconds))
        await ha.call_service(
            "timer",
            "start",
            {"entity_id": f"timer.{name}", "duration": duration},
        )
        TIMERS[name] = time.monotonic() + total_seconds
        _persist_timers()
        return f"Timer '{name}' started for {amount} {unit}."
