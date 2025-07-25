from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha

_ALIAS = {"i'm home": "script.house_arrival"}


class ScriptSkill(Skill):
    PATTERNS = [
        re.compile(r"i'?m home", re.I),
        re.compile(r"run (?P<name>[\w\s]+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("i"):
            entity = _ALIAS["i'm home"]
        else:
            name = match.group("name").strip()
            entity = f"script.{name.lower().replace(' ', '_')}"
        await ha.call_service("script", "turn_on", {"entity_id": entity})
        return f"Script {entity} triggered."
