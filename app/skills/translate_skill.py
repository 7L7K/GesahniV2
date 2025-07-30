from __future__ import annotations

import os
import re
import httpx

from .base import Skill

TRANSLATE_URL = os.getenv("TRANSLATE_URL", "http://localhost:5000")


class TranslateSkill(Skill):
    PATTERNS = [
        re.compile(r"translate ['\"]?(?P<text>.+?)['\"]? to (?P<lang>\w+)", re.I),
        re.compile(r"detect language of ['\"]?(?P<det>.+?)['\"]?", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("translate"):
            text = match.group("text")
            target = match.group("lang")
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{TRANSLATE_URL}/translate",
                    json={"q": text, "source": "auto", "target": target},
                )
                resp.raise_for_status()
                data = resp.json()
            return data.get("translatedText", "")
        det = match.group("det")
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{TRANSLATE_URL}/detect", json={"q": det})
            resp.raise_for_status()
            data = resp.json()
        if isinstance(data, list) and data:
            return data[0].get("language", "")
        return ""
