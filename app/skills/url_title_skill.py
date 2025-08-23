from __future__ import annotations

import re

import httpx

from .base import Skill


class UrlTitleSkill(Skill):
    PATTERNS = [
        re.compile(r"\b(?:what(?:'s| is) the )?title of (https?://\S+)", re.I),
        re.compile(r"\bfetch title (https?://\S+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        url = match.group(1)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text or ""
        except Exception:
            return "Could not fetch title."
        # crude title extraction
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if not m:
            return "No title found."
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        return title[:200] if title else "No title found."
