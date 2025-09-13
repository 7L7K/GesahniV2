"""
Fake Music Provider for Testing

In-memory implementation of MusicProvider interface.
Provides realistic playback simulation without external dependencies.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Iterable
from typing import Literal

from .base import Device, MusicProvider, PlaybackState, Track


class FakeProvider(MusicProvider):
    """Fake music provider with in-memory state for testing."""

    name = "fake"

    def __init__(self):
        # In-memory state
        self._tracks: dict[str, Track] = {}
        self._devices: dict[str, Device] = {}
        self._current_track: Track | None = None
        self._current_device: Device | None = None
        self._is_playing = False
        self._progress_ms = 0
        self._volume = 50
        self._shuffle = False
        self._repeat: Literal["off", "track", "context"] = "off"
        self._queue: list[Track] = []
        self._last_update = time.time()

        # Initialize with some fake data
        self._init_fake_data()

    def _init_fake_data(self):
        """Initialize fake tracks and devices."""
        # Fake tracks
        tracks_data = [
            ("track1", "Bohemian Rhapsody", "Queen", "A Night at the Opera", 355000),
            ("track2", "Stairway to Heaven", "Led Zeppelin", "Led Zeppelin IV", 482000),
            ("track3", "Hotel California", "Eagles", "Hotel California", 391000),
            ("track4", "Imagine", "John Lennon", "Imagine", 183000),
            ("track5", "Hey Jude", "The Beatles", "Hey Jude", 431000),
        ]

        for track_id, title, artist, album, duration in tracks_data:
            self._tracks[track_id] = Track(
                id=track_id,
                title=title,
                artist=artist,
                album=album,
                duration_ms=duration,
                explicit=False,  # Add missing explicit field
                provider=self.name,
            )

        # Fake devices
        devices_data = [
            ("device1", "Living Room Speaker", "speaker", True),
            ("device2", "Bedroom Speaker", "speaker", False),
            ("device3", "Kitchen Speaker", "speaker", False),
        ]

        for device_id, name, device_type, is_active in devices_data:
            self._devices[device_id] = Device(
                id=device_id,
                name=name,
                type=device_type,
                volume=50,
                active=is_active,
            )

            if is_active:
                self._current_device = self._devices[device_id]

        # Set initial track
        if self._tracks:
            self._current_track = list(self._tracks.values())[0]

    def capabilities(self) -> set[str]:
        return {
            "play", "pause", "resume", "next", "previous", "seek",
            "volume", "device_transfer", "queue", "search"
        }

    async def search(self, query: str, types: Iterable[str]) -> dict[str, list[Track]]:
        """Search for tracks (fake implementation)."""
        results = []
        query_lower = query.lower()

        for track in self._tracks.values():
            if (query_lower in track.title.lower() or
                query_lower in track.artist.lower() or
                query_lower in track.album.lower()):
                results.append(track)

        return {"track": results}

    async def play(self, entity_id: str, entity_type: str, *, device_id: str | None = None, position_ms: int | None = None) -> None:
        """Play a track or search result."""
        if entity_type == "track":
            if entity_id not in self._tracks:
                raise ValueError(f"Track not found: {entity_id}")
            self._current_track = self._tracks[entity_id]
        elif entity_type == "search":
            # Play first search result for the query
            results = await self.search(entity_id, ["track"])
            if results["track"]:
                self._current_track = results["track"][0]
            else:
                raise ValueError(f"No tracks found for query: {entity_id}")
        else:
            raise ValueError(f"Unsupported entity type: {entity_type}")

        if device_id:
            if device_id not in self._devices:
                raise ValueError(f"Device not found: {device_id}")
            self._current_device = self._devices[device_id]

        self._is_playing = True
        self._progress_ms = position_ms or 0
        self._last_update = time.time()

    async def pause(self) -> None:
        """Pause playback."""
        self._is_playing = False
        self._update_progress()

    async def resume(self) -> None:
        """Resume playback."""
        if self._current_track:
            self._is_playing = True
            self._last_update = time.time()

    async def next(self) -> None:
        """Skip to next track."""
        if not self._queue:
            # Create a simple queue from available tracks
            self._queue = list(self._tracks.values())

        if self._queue:
            # Find current track in queue and move to next
            current_idx = -1
            if self._current_track:
                try:
                    current_idx = self._queue.index(self._current_track)
                except ValueError:
                    current_idx = -1

            next_idx = (current_idx + 1) % len(self._queue)
            self._current_track = self._queue[next_idx]
            self._progress_ms = 0
            self._last_update = time.time()

    async def previous(self) -> None:
        """Skip to previous track."""
        if not self._queue:
            self._queue = list(self._tracks.values())

        if self._queue:
            current_idx = -1
            if self._current_track:
                try:
                    current_idx = self._queue.index(self._current_track)
                except ValueError:
                    current_idx = -1

            prev_idx = (current_idx - 1) % len(self._queue)
            self._current_track = self._queue[prev_idx]
            self._progress_ms = 0
            self._last_update = time.time()

    async def seek(self, position_ms: int) -> None:
        """Seek to position in current track."""
        if not self._current_track:
            raise ValueError("No track currently playing")

        if position_ms < 0 or position_ms > self._current_track.duration_ms:
            raise ValueError(f"Invalid position: {position_ms}ms")

        self._progress_ms = position_ms
        self._last_update = time.time()

    async def set_volume(self, level: int) -> None:
        """Set volume level (0-100)."""
        if level < 0 or level > 100:
            raise ValueError(f"Invalid volume level: {level}")

        self._volume = level
        if self._current_device:
            self._current_device.volume = level

    async def list_devices(self) -> list[Device]:
        """List available devices."""
        return list(self._devices.values())

    async def transfer_playback(self, device_id: str, force_play: bool = True) -> None:
        """Transfer playback to another device."""
        if device_id not in self._devices:
            raise ValueError(f"Device not found: {device_id}")

        self._current_device = self._devices[device_id]

        # Update active status
        for device in self._devices.values():
            device.active = (device.id == device_id)

    async def get_state(self) -> PlaybackState:
        """Get current playback state."""
        self._update_progress()

        device = self._current_device
        if device:
            device.volume = self._volume

        return PlaybackState(
            is_playing=self._is_playing,
            progress_ms=self._progress_ms,
            track=self._current_track,
            device=device,
            shuffle=self._shuffle,
            repeat=self._repeat,
        )

    async def add_to_queue(self, entity_id: str, entity_type: str) -> None:
        """Add track to queue."""
        if entity_type != "track":
            raise ValueError(f"Unsupported entity type for queue: {entity_type}")

        if entity_id not in self._tracks:
            raise ValueError(f"Track not found: {entity_id}")

        track = self._tracks[entity_id]
        self._queue.append(track)

    def _update_progress(self):
        """Update progress based on playing state and time elapsed."""
        if self._is_playing and self._current_track:
            elapsed = time.time() - self._last_update
            self._progress_ms += int(elapsed * 1000)

            # Clamp to track duration
            if self._progress_ms > self._current_track.duration_ms:
                self._progress_ms = self._current_track.duration_ms
                self._is_playing = False  # Auto-pause at end

            self._last_update = time.time()

    # Optional methods (raise NotImplementedError for unsupported features)
    async def create_playlist(self, name: str, track_ids: list[str]) -> None:
        raise NotImplementedError("Playlist creation not supported in fake provider")

    async def like_track(self, track_id: str) -> None:
        raise NotImplementedError("Track liking not supported in fake provider")

    async def recommendations(self, seeds: dict, params: dict) -> list[Track]:
        raise NotImplementedError("Recommendations not supported in fake provider")
