from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

HA_URL = os.getenv("HOME_ASSISTANT_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")


from .base import Device


class HomeAssistantRadioProvider:
    """Fallback provider that calls Home Assistant `media_player.play_media`.

    This provider assumes Home Assistant REST API is reachable and a long-lived
    token is available in `HOME_ASSISTANT_TOKEN`.
    """

    name = "ha"

    def __init__(self, ha_url: str | None = None, token: str | None = None) -> None:
        self.ha_url = ha_url or HA_URL
        self.token = token or HA_TOKEN

    async def play(self, device_id: str, context: dict[str, Any]) -> None:
        await self.play_url(context.get("media_content_id"), device_id)

    async def pause(self, device_id: str) -> None:
        url = f"{self.ha_url}/api/services/media_player/media_pause"
        payload = {"entity_id": device_id}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error("HA pause failed: %s %s", resp.status, text)
                    raise RuntimeError("Home Assistant pause failed")

    async def next(self, device_id: str) -> None:
        # HA may not support next for all players; best-effort via media_next_track
        url = f"{self.ha_url}/api/services/media_player/media_next_track"
        payload = {"entity_id": device_id}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error("HA next failed: %s %s", resp.status, text)
                    raise RuntimeError("Home Assistant next failed")

    async def previous(self, device_id: str) -> None:
        url = f"{self.ha_url}/api/services/media_player/media_previous_track"
        payload = {"entity_id": device_id}
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.post(url, json=payload, headers=headers) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error("HA previous failed: %s %s", resp.status, text)
                    raise RuntimeError("Home Assistant previous failed")

    async def list_devices(self) -> list[Device]:
        url = f"{self.ha_url}/api/states"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.error("HA devices failed: %s", resp.status)
                    return []
                data = await resp.json()
                # Filter media_player entities
                devices = [
                    Device(
                        id=s.get("entity_id", "media_player.unknown"),
                        name=(s.get("attributes", {}) or {}).get(
                            "friendly_name", s.get("entity_id", "")
                        ),
                        type="media_player",
                        volume=(s.get("attributes", {}) or {}).get("volume_level"),
                        active=(s.get("state") == "playing"),
                    )
                    for s in data
                    if s.get("entity_id", "").startswith("media_player.")
                ]
                return devices

    async def play_url(self, url: str | None, entity_id: str | None = None) -> None:
        if not url and os.getenv("HA_DEFAULT_RADIO_URL"):
            url = os.getenv("HA_DEFAULT_RADIO_URL")
        if not url:
            raise RuntimeError("no_url_provided")
        payload = {
            "entity_id": entity_id or "media_player.house",
            "media_content_id": url,
            "media_content_type": "music",
        }
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                f"{self.ha_url}/api/services/media_player/play_media",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    logger.error("HA play_url failed: %s %s", resp.status, text)
                    raise RuntimeError("Home Assistant play failed")
