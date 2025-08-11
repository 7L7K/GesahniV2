"""Spotify consent + cache scaffold."""

from dataclasses import dataclass


@dataclass
class SpotifyConfig:
    consent: bool = False
    scope: str = "user-read-playback-state user-modify-playback-state"


def disconnect() -> None:
    pass


