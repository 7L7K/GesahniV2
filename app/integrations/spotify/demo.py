from __future__ import annotations
import logging
import os
from typing import Any, Dict, List, Callable, Awaitable

logger = logging.getLogger(__name__)

def devices_demo() -> Dict[str, Any]:
    demo_data = {
        "devices": [
            {
                "id": "demo-device-1",
                "is_active": True,
                "is_restricted": False,
                "name": "King's Mac (Demo)",
                "type": "Computer",
                "volume_percent": 65,
            }
        ],
        "demo": True,
    }
    logger.info(f"🎵 DEMO SPOTIFY: Returning demo devices data: {demo_data}")
    return demo_data

async def maybe_devices(real_callable: Callable[[], Awaitable[Any]]) -> Any:
    if os.getenv("DEMO_MODE") == "1" or os.getenv("DISABLE_SPOTIFY") == "1":
        logger.info("🎵 DEMO SPOTIFY: Using demo devices (DEMO_MODE or DISABLE_SPOTIFY enabled)")
        return devices_demo()
    logger.info("🎵 SPOTIFY: Using real Spotify API for devices")
    return await real_callable()

def currently_playing_demo() -> Dict[str, Any]:
    return {
        "is_playing": True,
        "progress_ms": 42000,
        "item": {
            "name": "Demo Track",
            "artists": [{"name": "Demo Artist"}],
            "album": {"name": "Demo Album"},
            "duration_ms": 187000,
        },
        "demo": True,
    }

def maybe_currently_playing(real_callable):
    if os.getenv("DEMO_MODE") == "1" or os.getenv("DISABLE_SPOTIFY") == "1":
        return currently_playing_demo()
    return real_callable()
