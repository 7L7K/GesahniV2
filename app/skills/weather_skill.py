# app/skills/weather_skill.py

from __future__ import annotations

import os
import re
import httpx
import logging
from .base import Skill

log = logging.getLogger(__name__)

OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")
DEFAULT_CITY = os.getenv("CITY_NAME", "Detroit,US")


class WeatherSkill(Skill):
    PATTERNS = [
        # Pattern for "weather in Seattle"
        re.compile(r"\bweather in ([\w\s]+)", re.I),
        # Pattern for "what's the weather", "whats the weather", "what is the weather", "forecast", with/without today/now
        re.compile(
            r"\b(?:what(?:['’]s|s| is)? the weather|forecast)(?: today| now)?\b",
            re.I,
        ),
        # Fallback for anything with just "weather" in the text
        re.compile(r"\bweather\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        # Try to extract city if matched in "weather in <city>"
        if match.lastindex == 1:
            city = match.group(1).strip()
        else:
            city = DEFAULT_CITY

        if not OPENWEATHER_KEY:
            return "Weather API key not set."

        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/weather",
                    params={
                        "q": city,
                        "appid": OPENWEATHER_KEY,
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
            if temp is not None
            else f"No weather data for {city}."
        )
