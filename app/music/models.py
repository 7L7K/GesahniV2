from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Device:
    id: str
    name: str
    area: str | None = None
    provider: str | None = None


@dataclass
class Track:
    id: str
    title: str
    artist: str
    uri: str
    duration_ms: int


@dataclass
class QueueItem:
    id: str
    track: Track
    requested_by: str | None = None
    vibe: dict[str, Any] | None = None


