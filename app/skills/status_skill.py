from __future__ import annotations

import re
import time

from ..status import _request, llama_get_status
from .base import Skill

START_TIME = time.time()


class StatusSkill(Skill):
    PATTERNS = [re.compile(r"status", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        uptime = int(time.time() - START_TIME)
        try:
            await _request("GET", "/states")
            ha = "ok"
        except Exception:
            ha = "error"
        try:
            llama = (await llama_get_status())["status"]
        except Exception:
            llama = "error"
        return f"uptime: {uptime}s, ha: {ha}, llama: {llama}"
