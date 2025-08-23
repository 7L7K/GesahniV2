"""Media player overlay scaffold."""

from dataclasses import dataclass


@dataclass
class MediaOverlay:
    title: str | None = None
    is_playing: bool = False
    progress_seconds: int = 0
