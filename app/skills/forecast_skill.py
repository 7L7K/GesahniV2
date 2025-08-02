from __future__ import annotations

import datetime as _dt
import os
import re
from collections import defaultdict
import httpx
import logging

from .base import Skill

log = logging.getLogger(__name__)

OPENWEATHER_KEY = os.getenv("OPENWEATHER_API_KEY")
DEFAULT_CITY = os.getenv("CITY_NAME", "Detroit,US")


class ForecastSkill(Skill):
    PATTERNS = [
        re.compile(r"\b(?:3|three)[- ]day forecast(?: for ([\w\s]+))?", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        city = match.group(1).strip() if match.lastindex == 1 else DEFAULT_CITY
        if not OPENWEATHER_KEY:
            return "Weather API key not set."
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.openweathermap.org/data/2.5/forecast",
                    params={
                        "q": city,
                        "appid": OPENWEATHER_KEY,
                        "units": "imperial",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            log.exception("Forecast fetch failed")
            return f"Couldn't get the forecast for {city.title()}."

        temps: dict[str, list[float]] = defaultdict(list)
        for item in data.get("list", []):
            date = item.get("dt_txt", "").split(" ")[0]
            if not date:
                continue
            temps[date].append(item.get("main", {}).get("temp"))

        dates = sorted(temps.keys())[:3]
        parts = []
        for d in dates:
            values = [t for t in temps[d] if isinstance(t, (int, float))]
            if not values:
                continue
            day = _dt.datetime.strptime(d, "%Y-%m-%d").strftime("%a")
            parts.append(f"{day}: {max(values):.0f}/{min(values):.0f}\u00b0F")
        return " | ".join(parts) if parts else f"No forecast data for {city.title()}."
