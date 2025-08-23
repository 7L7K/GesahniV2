from __future__ import annotations

import re

from .. import home_assistant as ha
from .base import Skill

_ALIAS = {"i'm home": "script.house_arrival"}


class ScriptSkill(Skill):
    PATTERNS = [
        re.compile(r"i'?m home", re.I),
        # Require a word boundary before 'run' to avoid matching inside words
        # like "Lebrun" while still allowing natural phrasing like
        # "can you run bedtime routine"
        re.compile(r"\b(?:run|trigger|start)\s+(?P<name>[\w\s]+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("i"):
            entity = _ALIAS["i'm home"]
        else:
            name = match.group("name").strip()
            # resolve first to support user aliases like "bedtime routine"
            results = await ha.resolve_entity(name)
            entity = results[0] if results else f"script.{name.lower().replace(' ', '_')}"
        await ha.call_service("script", "turn_on", {"entity_id": entity})
        return f"Script {entity} triggered."
