from __future__ import annotations

import re

from .. import home_assistant as ha
from .base import Skill


class SceneSkill(Skill):
    PATTERNS = [
        re.compile(r"(?:activate|turn on|enable) (?P<name>[\w\s]+) scene", re.I),
        re.compile(r"(?P<name>[\w\s]+) mode", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        name = match.group("name").strip()
        entity = (await ha.resolve_entity(name))[0]
        await ha.call_service("scene", "turn_on", {"entity_id": entity})
        return f"Activated {name.title()} scene."
