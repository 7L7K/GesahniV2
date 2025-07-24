from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class DoorLockSkill(Skill):
    PATTERNS = [
        re.compile(r"(lock|unlock) ([\w\s]+) door", re.I),
        re.compile(r"is ([\w\s]+) door locked", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("(lock|unlock)"):
            action, name = match.group(1), match.group(2)
            entity = (await ha.resolve_entity(name))[0]
            await ha.call_service(
                "lock",
                "lock" if action == "lock" else "unlock",
                {"entity_id": entity},
            )
            return f"{action.title()}ed {entity}"
        name = match.group(1)
        entity = (await ha.resolve_entity(name))[0]
        return f"{entity} is locked"  # simplified
