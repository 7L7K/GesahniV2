from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass
class Track:
    id: str
    title: str
    artist: str
    album: str
    duration_ms: int
    explicit: bool
    provider: str


@dataclass
class Album:
    id: str
    title: str
    artist: str
    provider: str


@dataclass
class Artist:
    id: str
    name: str
    provider: str


@dataclass
class Playlist:
    id: str
    name: str
    owner: str
    provider: str


@dataclass
class Device:
    id: str
    name: str
    type: str
    volume: int | None
    active: bool


@dataclass
class PlaybackState:
    is_playing: bool
    progress_ms: int
    track: Track | None
    device: Device | None
    shuffle: bool
    repeat: Literal["off", "track", "context"]


class MusicProvider(Protocol):
    name: str

    def capabilities(self) -> set[str]:
        ...  # e.g. {"play","queue","device_transfer","search","playlist"}

    async def search(self, query: str, types: Iterable[str]) -> dict[str, list[Track | Artist | Album | Playlist]]: ...

    async def play(self, entity_id: str, entity_type: str, *, device_id: str | None = None, position_ms: int | None = None) -> None: ...

    async def pause(self) -> None: ...

    async def resume(self) -> None: ...

    async def next(self) -> None: ...

    async def previous(self) -> None: ...

    async def seek(self, position_ms: int) -> None: ...

    async def set_volume(self, level: int) -> None: ...  # 0–100

    async def list_devices(self) -> list[Device]: ...

    async def transfer_playback(self, device_id: str, force_play: bool = True) -> None: ...

    async def get_state(self) -> PlaybackState: ...

    async def add_to_queue(self, entity_id: str, entity_type: str) -> None: ...

    async def create_playlist(self, name: str, track_ids: list[str]) -> Playlist | None: ...

    async def like_track(self, track_id: str) -> None: ...

    async def recommendations(self, seeds: dict, params: dict) -> list[Track]: ...


