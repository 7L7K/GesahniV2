from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class Device:
    id: str
    name: str
    area: Optional[str] = None
    provider: Optional[str] = None


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
    requested_by: Optional[str] = None
    vibe: Optional[Dict[str, Any]] = None


