from __future__ import annotations

import logging
import os
import re

import httpx

from .base import Skill

log = logging.getLogger(__name__)

DEFAULT_ORIGIN = os.getenv("CITY_NAME", "Detroit,US")
GEOCODE_URL = "https://nominatim.openstreetmap.org/search"
ROUTE_URL = "https://router.project-osrm.org/route/v1/driving"


class TrafficSkill(Skill):
    PATTERNS = [
        re.compile(r"traffic to ([\w\s,]+)", re.I),
        re.compile(r"how long to drive to ([\w\s,]+)", re.I),
    ]

    async def _geocode(
        self, client: httpx.AsyncClient, place: str
    ) -> tuple[float, float] | None:
        resp = await client.get(
            GEOCODE_URL,
            params={"q": place, "format": "json", "limit": 1},
            headers={"User-Agent": "GesahniV2"},
        )
        resp.raise_for_status()
        data = resp.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])

    async def run(self, prompt: str, match: re.Match) -> str:
        dest = match.group(1).strip()
        origin = DEFAULT_ORIGIN
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                orig = await self._geocode(client, origin)
                destc = await self._geocode(client, dest)
                if not orig or not destc:
                    return f"Couldn't find route to {dest}."
                o_lat, o_lon = orig
                d_lat, d_lon = destc
                resp = await client.get(
                    f"{ROUTE_URL}/{o_lon},{o_lat};{d_lon},{d_lat}",
                    params={"overview": "false"},
                )
                resp.raise_for_status()
                data = resp.json()
                duration = data.get("routes", [{}])[0].get("duration")
                if duration is None:
                    return f"Couldn't get traffic info for {dest}."
        except Exception:
            log.exception("traffic lookup failed")
            return f"Couldn't get traffic info for {dest}."
        minutes = int(duration / 60)
        return f"Driving to {dest.title()} takes about {minutes} minutes."
