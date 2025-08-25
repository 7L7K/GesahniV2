from __future__ import annotations
# app/skills/joke_skill.py

import re

import httpx

from .base import Skill


class JokeSkill(Skill):
    PATTERNS = [
        re.compile(r"tell me a joke", re.I),
        re.compile(r"^joke$", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        url = "https://official-joke-api.appspot.com/random_joke"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
        setup = data.get("setup")
        punchline = data.get("punchline")
        if setup and punchline:
            return f"{setup} {punchline}"
        return "I couldn't think of a joke right now."
