from __future__ import annotations

import re
import httpx

from .base import Skill


class SearchSkill(Skill):
    PATTERNS = [
        re.compile(r"search for (.+)", re.I),
        re.compile(r"who is (.+)", re.I),
        re.compile(r"what is (.+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        query = match.group(1)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={"q": query, "format": "json", "no_redirect": "1", "no_html": "1"},
            )
            resp.raise_for_status()
            data = resp.json()
        for key in ("Answer", "AbstractText", "Definition" ):
            val = data.get(key)
            if val:
                return val
        return "No short answer found."
