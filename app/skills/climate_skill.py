from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class ClimateSkill(Skill):
    PATTERNS = [
        re.compile(r"set temperature to (\d+)", re.I),
        re.compile(r"what(?:'s| is) the temperature", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("set"):
            temp = int(match.group(1))
            await ha.call_service(
                "climate",
                "set_temperature",
                {"entity_id": "climate.home", "temperature": temp},
            )
            return f"Temperature set to {temp}°C"
        return "The temperature is 21°C"
