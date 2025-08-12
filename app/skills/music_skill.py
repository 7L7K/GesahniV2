from __future__ import annotations

import re
import json
import pathlib

from .base import Skill
from .. import home_assistant as ha


_MAP_PATH = pathlib.Path(__file__).with_name("artist_map.json")
try:
    ARTIST_MAP: dict[str, str] = json.loads(_MAP_PATH.read_text())
except Exception:
    ARTIST_MAP = {}


class MusicSkill(Skill):
    PATTERNS = [
        re.compile(r"\b(play|pause|stop) music\b", re.I),
        re.compile(r"\bplay (?P<artist>[\w\.,\-\s]+)$", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if "artist" in match.groupdict() and match.group("artist").lower() != "music":
            artist = match.group("artist").strip()
            uri = ARTIST_MAP.get(artist.lower())
            if not uri:
                return f"Unknown artist {artist}."
            await ha.call_service(
                "media_player",
                "play_media",
                {
                    "entity_id": "media_player.house",
                    "media_content_id": uri,
                    "media_content_type": "music",
                },
            )
            return f"Playing {artist}"

        action = match.group(1).lower() if match.groups() else "play"
        service = "media_play" if action == "play" else ("media_pause" if action == "pause" else "media_stop")
        await ha.call_service(
            "media_player", service, {"entity_id": "media_player.house"}
        )
        return f"Music {action}ed"
