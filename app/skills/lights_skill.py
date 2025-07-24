from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class LightsSkill(Skill):
    PATTERNS = [
        re.compile(r"turn (on|off) ([\w\s]+) lights", re.I),
        re.compile(r"set ([\w\s]+) lights to (\d+)%", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("turn"):
            action, name = match.group(1), match.group(2)
            entity = (await ha.resolve_entity(name))[0]
            service = ha.turn_on if action.lower() == "on" else ha.turn_off
            await service(entity)
            return f"{action.title()}ed {entity}"
        name, level = match.group(1), int(match.group(2))
        entity = (await ha.resolve_entity(name))[0]
        await ha.call_service("light", "turn_on", {"entity_id": entity, "brightness_pct": level})
        return f"Set {entity} to {level}%"
