# app/skills/weather_skill.py
from __future__ import annotations

import os               # ✅ missing
import re
import httpx
import logging
from .base import Skill  # ✅ missing

log = logging.getLogger(__name__)

OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")
DEFAULT_CITY    = os.getenv("CITY_NAME", "Detroit,US")

class WeatherSkill(Skill):
    PATTERNS = [
        re.compile(r"\bweather in ([\w\s]+)", re.I),
        re.compile(r"\b(?:what(?:'s| is)? the weather|forecast)\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        city = match.group(1).strip() if match.lastindex == 1 else DEFAULT_CITY

        if not OPENWEATHER_KEY:
            return "Weather API key not set."

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={
                        "q": city,
                        "appid": OPENWEATHER_KEY,   # use the var we defined
                        "units": "imperial",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            log.exception("Weather fetch failed")
            return f"Couldn’t get the weather for {city.title()}."

        temp = data.get("main", {}).get("temp")
        desc = data.get("weather", [{}])[0].get("description", "")
        return (
            f"{city.title()} is currently {desc}, around {temp:.0f}°F."
            if temp
            else f"No weather data for {city}."
        )
