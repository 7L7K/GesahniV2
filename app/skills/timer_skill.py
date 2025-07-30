from __future__ import annotations

import re
import time
from datetime import timedelta
from typing import Dict

from .base import Skill
from .. import home_assistant as ha


_TIMERS: Dict[str, float] = {}


class TimerSkill(Skill):
    PATTERNS = [
        re.compile(r"(?:start|set) a timer for (?P<num>\d+) (?P<unit>seconds|minutes)", re.I),
        re.compile(r"(?:start|set) (?P<name>[\w\s]+?) timer for (?P<num>\d+) (?P<unit>seconds|minutes)", re.I),
        re.compile(r"cancel (?P<cname>[\w\s]+?) timer", re.I),
        re.compile(r"how long (?:is left|left) on (?P<qname>[\w\s]+?) timer", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        gd = match.groupdict()
        if gd.get("cname"):
            name = gd["cname"].strip().lower()
            if name in _TIMERS:
                del _TIMERS[name]
                return f"Canceled {name} timer."
            return f"No timer named {name}."

        if gd.get("qname"):
            name = gd["qname"].strip().lower()
            if name not in _TIMERS:
                return f"No timer named {name}."
            remaining = int(_TIMERS[name] - time.time())
            return f"{remaining} seconds left on {name} timer." if remaining > 0 else f"{name} timer done."

        name = (gd.get("name") or "default").strip().lower()
        amount = int(gd["num"])
        unit = gd["unit"].lower()
        total_seconds = amount * (60 if unit.startswith("minute") else 1)
        duration = str(timedelta(seconds=total_seconds))
        _TIMERS[name] = time.time() + total_seconds
        if name == "default":  # keep old behavior
            await ha.call_service(
                "timer",
                "start",
                {"entity_id": "timer.gesahni", "duration": duration},
            )
        return f"Timer '{name}' started for {amount} {unit}."
