from __future__ import annotations

import random
import re
import httpx
from .base import Skill

# Simple fallback jokes in case the API request fails
JOKES = [
    {"setup": "Why did the scarecrow win an award?", "punchline": "Because he was outstanding in his field."},
    {"setup": "Why don't scientists trust atoms?", "punchline": "Because they make up everything."},
]


class JokeSkill(Skill):
    PATTERNS = [re.compile(r"\bjoke\b", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("https://official-joke-api.appspot.com/jokes/random")
                resp.raise_for_status()
                data = resp.json()
                setup = data.get("setup")
                punch = data.get("punchline")
                if setup and punch:
                    return f"{setup} {punch}"
        except Exception:
            pass
        joke = random.choice(JOKES)
        return f"{joke['setup']} {joke['punchline']}"
