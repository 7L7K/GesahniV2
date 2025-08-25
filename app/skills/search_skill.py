from __future__ import annotations
# app/skills/search_skill.py

import re

import httpx

from .base import Skill


class SearchSkill(Skill):
    # Only match true “search” intents, not generic “what is the weather?”
    PATTERNS = [
        re.compile(r"^search(?: for)? (?P<query>.+)", re.I),
        re.compile(r"^who (?:is|was) (?P<query>.+)", re.I),
        re.compile(r"^what (?:is|are) (?P<query>.+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        query = match.group("query").strip()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_redirect": "1",
                        "no_html": "1",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return "Search service unreachable."
        # Return the first non-empty answer field
        for key in ("Answer", "AbstractText", "Definition"):
            if val := data.get(key):
                return val
        # Fallback to first heading, if available
        related = data.get("RelatedTopics") or []
        if isinstance(related, list) and related:
            first = related[0]
            if isinstance(first, dict) and first.get("Text"):
                return first.get("Text")
        return "No short answer found."
