from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class RokuSkill(Skill):
    PATTERNS = [re.compile(r"launch ([\w\s]+) on roku", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        app = match.group(1).strip()
        await ha.call_service("remote", "send_command", {"entity_id": "remote.roku", "command": app})
        return f"Launching {app} on Roku"
