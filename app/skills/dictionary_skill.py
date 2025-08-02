# app/skills/dictionary_skill.py
from __future__ import annotations

import re

import httpx

from .base import Skill


class DictionarySkill(Skill):
    PATTERNS = [
        re.compile(r"^define (?P<word>\w+)", re.I),
        re.compile(r"^synonyms? for (?P<word>\w+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        word = match.group("word").lower()
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return f"No definition found for '{word}'."
            data = resp.json()
        try:
            meanings = data[0]["meanings"][0]
            definition = meanings["definitions"][0]["definition"]
            synonyms = meanings.get("synonyms", [])
            if synonyms:
                syn = ", ".join(synonyms[:5])
                return f"{word}: {definition} Synonyms: {syn}"
            return f"{word}: {definition}"
        except Exception:
            return f"No definition found for '{word}'."
