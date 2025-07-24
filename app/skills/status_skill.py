from __future__ import annotations

import os
import re
import time

from .base import Skill
from ..status import llama_get_status, _request

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
