"""Music connection card scaffold."""

from dataclasses import dataclass


@dataclass
class MusicCard:
    provider: str | None = None  # e.g., "spotify", "apple"
    is_connected: bool = False
