"""Photos connection card scaffold."""

from dataclasses import dataclass


@dataclass
class PhotosCard:
    provider: str | None = None  # e.g., "shared_album"
    is_connected: bool = False
