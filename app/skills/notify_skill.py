from __future__ import annotations

import re

from .. import home_assistant as ha
from .base import Skill


class NotifySkill(Skill):
    PATTERNS = [
        re.compile(r"ping my phone", re.I),
        re.compile(r"notify (?P<msg>.+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        message = match.group("msg") if "msg" in match.groupdict() else "Ping"
        await ha.call_service(
            "notify",
            "mobile_app_phone",
            {"message": message},
        )
        return "Notification sent."
