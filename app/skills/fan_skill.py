from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class FanSkill(Skill):
    PATTERNS = [
        re.compile(r"turn (on|off) (?:the )?(?P<name>[\w\s]*(?:fan|air purifier|air filter))", re.I)
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        action = match.group(1).lower()
        name = match.group("name").strip()
        entity = (await ha.resolve_entity(name))[0]
        domain = entity.split(".")[0]
        service = "turn_on" if action == "on" else "turn_off"
        await ha.call_service(domain, service, {"entity_id": entity})
        return f"{action.title()}ed {name}."
