from __future__ import annotations

import re

from .base import Skill
from .. import home_assistant as ha


class MusicSkill(Skill):
    PATTERNS = [re.compile(r"(play|pause) music", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        action = match.group(1).lower()
        service = "media_play" if action == "play" else "media_pause"
        await ha.call_service("media_player", service, {"entity_id": "media_player.house"})
        return f"Music {action}ed"
