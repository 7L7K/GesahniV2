# app/skills/search_skill.py
from __future__ import annotations

import re
import httpx
from .base import Skill

class SearchSkill(Skill):
    # Only match true “search” intents, not generic “what is the weather?”
    PATTERNS = [
        re.compile(r"^search(?: for)? (?P<query>.+)", re.I),
        re.compile(r"^who is (?P<query>.+)", re.I),
        re.compile(r"^what is (?P<query>.+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        query = match.group("query").strip()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": query,
                    "format": "json",
                    "no_redirect": "1",
                    "no_html": "1",
                },
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()
        # Return the first non-empty answer field
        for key in ("Answer", "AbstractText", "Definition"):
            if val := data.get(key):
                return val
        return "No short answer found."
