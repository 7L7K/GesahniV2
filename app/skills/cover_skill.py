from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class CoverSkill(Skill):
    PATTERNS = [re.compile(r"(open|close) (?P<name>[\w\s]+)", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        action = match.group(1).lower()
        name = match.group("name").strip()
        entity = (await ha.resolve_entity(name))[0]
        service = "open_cover" if action == "open" else "close_cover"
        await ha.call_service("cover", service, {"entity_id": entity})
        return f"{action.title()}ed {name}."
