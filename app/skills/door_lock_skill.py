from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class DoorLockSkill(Skill):
    PATTERNS = [
        re.compile(r"\b(lock|unlock) ([\w\s]+) door\b", re.I),
        re.compile(r"\bis ([\w\s]+) door locked\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("\\b(lock|unlock)"):
            action, name = match.group(1), match.group(2)
            results = await ha.resolve_entity(name)
            if not results:
                return f"I couldn't find “{name}”."
            entity = results[0]
            await ha.call_service(
                "lock",
                "lock" if action == "lock" else "unlock",
                {"entity_id": entity},
            )
            return f"{action.title()}ed {entity}"
        name = match.group(1)
        results = await ha.resolve_entity(name)
        if not results:
            return f"I couldn't find “{name}”."
        entity = results[0]
        return f"{entity} is locked"  # simplified
