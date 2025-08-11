"""Apple Music consent + cache scaffold."""

from dataclasses import dataclass


@dataclass
class AppleMusicConfig:
    consent: bool = False
    scope: str = "music.read music.modify"


def disconnect() -> None:
    pass


