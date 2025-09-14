from __future__ import annotations

import json
import pathlib
import re

from .. import home_assistant as ha
from ..music.orchestrator import MusicOrchestrator
from ..music.providers.spotify_provider import SpotifyProvider
from .base import Skill

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
        # Use orchestrator for general play/pause if available; fall back to HA service
        provider = SpotifyProvider()
        orch = MusicOrchestrator(provider=provider)
        try:
            if action == "play":
                await orch.play("media_player.house", {})
            elif action == "pause":
                await orch.pause("media_player.house")
            else:
                await ha.call_service(
                    "media_player", "media_stop", {"entity_id": "media_player.house"}
                )
            return f"Music {action}ed"
        except Exception:
            # best-effort fallback to HA
            service = (
                "media_play"
                if action == "play"
                else ("media_pause" if action == "pause" else "media_stop")
            )
            await ha.call_service(
                "media_player", service, {"entity_id": "media_player.house"}
            )
            return f"Music {action}ed (via HA fallback)"
