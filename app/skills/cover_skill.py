from __future__ import annotations

import re

from .. import home_assistant as ha
from .base import Skill


class CoverSkill(Skill):
    PATTERNS = [
        re.compile(
            r"\b(open|close) (?P<name>[\w\s]+?)(?: (?:cover|blind|blinds|garage|shades?))?\b",
            re.I,
        )
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        action = match.group(1).lower()
        name = match.group("name").strip()
        # resolve_entity returns list; handle no matches
        results = await ha.resolve_entity(name)
        if not results:
            return f"I couldn't find “{name}”."
        entity = results[0]
        service = "open_cover" if action == "open" else "close_cover"
        await ha.call_service("cover", service, {"entity_id": entity})
        return f"{action.title()}ed {name}."
