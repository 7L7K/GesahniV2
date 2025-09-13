from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Device:
    id: str
    name: str
    area: str | None = None
    provider: str | None = None
    type: str = "speaker"
    volume_percent: int = 50
    is_active: bool = False


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str | None = None
    uri: str = ""
    duration_ms: int = 0
    explicit: bool = False
    provider: str = "unknown"


@dataclass
class QueueItem:
    id: str
    track: Track
    requested_by: str | None = None
    vibe: dict[str, Any] | None = None


@dataclass
class PlayerState:
    """Comprehensive player state model with serialization and hashing."""
    is_playing: bool = False
    progress_ms: int = 0
    track: Track | None = None
    device: Device | None = None
    queue: list[QueueItem] = field(default_factory=list)
    shuffle: bool = False
    repeat: str = "off"  # off, track, context
    volume_percent: int = 50
    provider: str = "unknown"
    server_ts_at_position: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dictionary for JSON transmission."""
        return {
            "is_playing": self.is_playing,
            "progress_ms": self.progress_ms,
            "track": self.track.to_dict() if self.track else None,
            "device": self.device.to_dict() if self.device else None,
            "queue": [item.to_dict() for item in self.queue],
            "shuffle": self.shuffle,
            "repeat": self.repeat,
            "volume_percent": self.volume_percent,
            "provider": self.provider,
            "server_ts_at_position": self.server_ts_at_position,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlayerState:
        """Deserialize state from dictionary."""
        track = Track.from_dict(data["track"]) if data.get("track") else None
        device = Device.from_dict(data["device"]) if data.get("device") else None
        queue = [QueueItem.from_dict(item) for item in data.get("queue", [])]

        return cls(
            is_playing=data.get("is_playing", False),
            progress_ms=data.get("progress_ms", 0),
            track=track,
            device=device,
            queue=queue,
            shuffle=data.get("shuffle", False),
            repeat=data.get("repeat", "off"),
            volume_percent=data.get("volume_percent", 50),
            provider=data.get("provider", "unknown"),
            server_ts_at_position=data.get("server_ts_at_position", time.time()),
        )

    def state_hash(self) -> str:
        """Generate a hash representing the current state for change detection."""
        # Create a normalized representation for hashing
        hash_data = {
            "is_playing": self.is_playing,
            "progress_ms": self.progress_ms // 1000,  # Round to seconds for stability
            "track_id": self.track.id if self.track else None,
            "device_id": self.device.id if self.device else None,
            "queue_ids": [item.track.id for item in self.queue],
            "shuffle": self.shuffle,
            "repeat": self.repeat,
            "volume_percent": self.volume_percent,
            "provider": self.provider,
        }

        # Convert to stable JSON string and hash
        json_str = json.dumps(hash_data, sort_keys=True, separators=(",", ":"))
        return hashlib.md5(json_str.encode()).hexdigest()

    def clone(self) -> PlayerState:
        """Create a deep copy of the state."""
        return self.from_dict(self.to_dict())

    def update_progress(self, new_progress_ms: int | None = None) -> None:
        """Update progress and server timestamp."""
        if new_progress_ms is not None:
            self.progress_ms = new_progress_ms
        self.server_ts_at_position = time.time()


# Extend existing models with serialization methods
Track.to_dict = lambda self: {
    "id": self.id,
    "title": self.title,
    "artist": self.artist,
    "album": self.album,
    "uri": self.uri,
    "duration_ms": self.duration_ms,
    "explicit": self.explicit,
    "provider": self.provider,
}

Track.from_dict = classmethod(lambda cls, data: cls(**data))

Device.to_dict = lambda self: {
    "id": self.id,
    "name": self.name,
    "area": self.area,
    "provider": self.provider,
    "type": self.type,
    "volume_percent": self.volume_percent,
    "is_active": self.is_active,
}

Device.from_dict = classmethod(lambda cls, data: cls(**data))

QueueItem.to_dict = lambda self: {
    "id": self.id,
    "track": self.track.to_dict(),
    "requested_by": self.requested_by,
    "vibe": self.vibe,
}

QueueItem.from_dict = classmethod(lambda cls, data: cls(
    id=data["id"],
    track=Track.from_dict(data["track"]),
    requested_by=data.get("requested_by"),
    vibe=data.get("vibe"),
))


