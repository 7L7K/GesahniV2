from __future__ import annotations

import os
import re
import httpx

from .base import Skill

TRANSLATE_URL = os.getenv("TRANSLATE_URL", "http://localhost:5000")


class TranslateSkill(Skill):
    PATTERNS = [
        re.compile(r"translate ['\"]?(?P<txt>.+?)['\"]? to (?P<lang>\w+)", re.I),
        re.compile(r"what language is ['\"]?(?P<det>.+?)['\"]?\??", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.groupdict().get("txt"):
            text = match.group("txt")
            lang = match.group("lang")
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{TRANSLATE_URL.rstrip('/')}/translate",
                    json={"q": text, "source": "auto", "target": lang},
                )
                data = resp.json()
            return data.get("translatedText", "Unable to translate")
        text = match.group("det")
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{TRANSLATE_URL.rstrip('/')}/detect",
                data={"q": text},
            )
            data = resp.json()
        return data[0].get("language") if data else "unknown"
