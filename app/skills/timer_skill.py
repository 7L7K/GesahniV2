from __future__ import annotations

import re
import time
from datetime import timedelta

from .base import Skill
from .. import home_assistant as ha


TIMERS: dict[str, float] = {}


class TimerSkill(Skill):
    PATTERNS = [
        re.compile(
            r"(?:start|set) (?:(?P<name>\w+) )?timer for (?P<amount>\d+) (?P<unit>seconds|minutes)",
            re.I,
        ),
        re.compile(r"cancel (?:(?P<cname>\w+) )?timer", re.I),
        re.compile(r"how long left on (?:(?P<qname>\w+) )?timer", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        groups = match.groupdict()
        if "cname" in groups and groups["cname"] is not None:
            name = groups["cname"] or "gesahni"
            await ha.call_service("timer", "cancel", {"entity_id": f"timer.{name}"})
            TIMERS.pop(name, None)
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
        total_seconds = amount * (60 if unit.startswith("minute") else 1)
        duration = str(timedelta(seconds=total_seconds))
        await ha.call_service(
            "timer",
            "start",
            {"entity_id": f"timer.{name}", "duration": duration},
        )
        TIMERS[name] = time.monotonic() + total_seconds
        return f"Timer '{name}' started for {amount} {unit}."
