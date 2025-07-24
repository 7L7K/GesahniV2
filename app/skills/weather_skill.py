from __future__ import annotations

import os
import re
from typing import Optional

import httpx

from .base import Skill

OPENWEATHER_KEY = os.getenv("OPENWEATHER_KEY", "test")


class WeatherSkill(Skill):
    PATTERNS = [re.compile(r"weather in ([\w\s]+)", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        city = match.group(1).strip()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": OPENWEATHER_KEY, "units": "metric"},
            )
        data = resp.json()
        temp = data.get("main", {}).get("temp")
        return f"{city.title()} is {temp}°C" if temp is not None else "weather error"
