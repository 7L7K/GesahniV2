# app/skills/dictionary_skill.py
from __future__ import annotations

import re

import httpx

from .base import Skill


class DictionarySkill(Skill):
    PATTERNS = [
        re.compile(r"\bdefine (?P<word>[\w\-']+)\b", re.I),
        re.compile(r"\bsynonyms? (?:for|of) (?P<word>[\w\-']+)\b", re.I),
        re.compile(r"\bwhat does (?P<word>[\w\-']+) mean\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        word = match.group("word").lower()
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return f"No definition found for '{word}'."
                data = resp.json()
        except Exception:
            return "Dictionary service unreachable."
        try:
            # Prefer noun/verb meanings when present
            meanings_list = data[0].get("meanings", [])
            if not meanings_list:
                return f"No definition found for '{word}'."
            # pick the first meaning with definitions
            chosen = next((m for m in meanings_list if m.get("definitions")), meanings_list[0])
            definition = chosen["definitions"][0].get("definition", "")
            synonyms = chosen.get("synonyms", [])
            if synonyms:
                syn = ", ".join(synonyms[:5])
                return f"{word}: {definition} Synonyms: {syn}"
            return f"{word}: {definition}"
        except Exception:
            return f"No definition found for '{word}'."
