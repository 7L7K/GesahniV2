from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from ...integrations.spotify.client import SpotifyClient, SpotifyAuthError

logger = logging.getLogger(__name__)


class SpotifyProvider:
    """Spotify provider using the new unified integration for playback and device management."""

    def __init__(self, user_id: str = "default") -> None:
        self.user_id = user_id
        self.client = SpotifyClient(user_id)

    async def _ensure_client(self) -> SpotifyClient:
        """Ensure we have a client with valid tokens."""
        return self.client

    async def play(self, device_id: str, context: Dict[str, Any]) -> None:
        """Start playback with the given context."""
        try:
            client = await self._ensure_client()
            uris = context.get("uris")
            context_uri = context.get("context_uri")

            success = await client.play(uris=uris, context_uri=context_uri)
            if not success:
                raise RuntimeError("Spotify play failed")
        except SpotifyAuthError as e:
            logger.error(f"Spotify play failed: {e}")
            raise RuntimeError("Spotify authentication failed")

    async def pause(self, device_id: str) -> None:
        """Pause playback."""
        try:
            client = await self._ensure_client()
            success = await client.pause()
            if not success:
                raise RuntimeError("Spotify pause failed")
        except SpotifyAuthError as e:
            logger.error(f"Spotify pause failed: {e}")
            raise RuntimeError("Spotify authentication failed")

    async def next(self, device_id: str) -> None:
        """Skip to next track."""
        try:
            client = await self._ensure_client()
            success = await client.next_track()
            if not success:
                raise RuntimeError("Spotify next failed")
        except SpotifyAuthError as e:
            logger.error(f"Spotify next failed: {e}")
            raise RuntimeError("Spotify authentication failed")

    async def previous(self, device_id: str) -> None:
        """Skip to previous track."""
        try:
            client = await self._ensure_client()
            success = await client.previous_track()
            if not success:
                raise RuntimeError("Spotify previous failed")
        except SpotifyAuthError as e:
            logger.error(f"Spotify previous failed: {e}")
            raise RuntimeError("Spotify authentication failed")

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get available playback devices."""
        try:
            client = await self._ensure_client()
            devices = await client.get_devices()
            return devices
        except SpotifyAuthError as e:
            logger.error(f"Spotify get_devices failed: {e}")
            return []


