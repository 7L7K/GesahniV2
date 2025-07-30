from __future__ import annotations

import re
import httpx

from .base import Skill


class SearchSkill(Skill):
    PATTERNS = [re.compile(r"(?:search|lookup) (?:for )?(?P<q>.+)", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        query = match.group("q")
        url = "https://api.duckduckgo.com/"
        params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url, params=params)
                data = resp.json()
        except Exception:
            return "Search failed"
        text = data.get("AbstractText") or data.get("Answer")
        return text if text else "No concise answer found"
