from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class VacuumSkill(Skill):
    PATTERNS = [
        re.compile(r"start vacuum", re.I),
        re.compile(r"stop vacuum", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if "start" in match.re.pattern:
            await ha.call_service("vacuum", "start", {"entity_id": "vacuum.house"})
            return "Vacuum started"
        await ha.call_service("vacuum", "stop", {"entity_id": "vacuum.house"})
        return "Vacuum stopped"
