from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class LibrespotProvider:
    """Stub provider for librespot-based playback.

    This is a minimal stub for v1: it will raise NotImplementedError for
    advanced flows and is intended to be replaced by a real librespot bridge.
    """

    async def play(self, device_id: str, context: dict[str, Any]) -> None:
        raise NotImplementedError("LibrespotProvider.play not implemented")

    async def pause(self, device_id: str) -> None:
        raise NotImplementedError("LibrespotProvider.pause not implemented")

    async def next(self, device_id: str) -> None:
        raise NotImplementedError("LibrespotProvider.next not implemented")

    async def previous(self, device_id: str) -> None:
        raise NotImplementedError("LibrespotProvider.previous not implemented")

    async def get_devices(self) -> list[dict[str, Any]]:
        return []


