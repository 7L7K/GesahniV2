"""Shared album photos consent + cache scaffold."""

from dataclasses import dataclass


@dataclass
class SharedAlbumConfig:
    consent: bool = False
    provider: str = "apple"


def disconnect() -> None:
    pass


