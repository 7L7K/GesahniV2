import os
from typing import TYPE_CHECKING

from .orchestrator import MusicOrchestrator

if TYPE_CHECKING:
    from .providers.base import MusicProvider
else:
    # Import for runtime when not in TYPE_CHECKING mode
    from .providers.base import MusicProvider


def get_provider() -> MusicProvider:
    """Get the configured music provider."""
    provider_name = os.getenv("MUSIC_PROVIDER", "fake").lower().strip()

    if provider_name == "fake":
        from .providers.fake import FakeProvider

        return FakeProvider()
    elif provider_name == "spotify":
        from .providers.spotify_provider import SpotifyProvider

        return SpotifyProvider()
    elif provider_name == "librespot":
        from .providers.librespot_provider import LibrespotProvider

        return LibrespotProvider()
    elif provider_name == "ha":
        from .providers.home_assistant_radio import HomeAssistantRadioProvider

        return HomeAssistantRadioProvider()
    else:
        # Default to fake provider
        from .providers.fake import FakeProvider

        return FakeProvider()


__all__ = ["MusicOrchestrator", "get_provider"]
