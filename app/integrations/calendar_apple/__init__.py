"""Apple Calendar consent + cache scaffold."""

from dataclasses import dataclass


@dataclass
class AppleCalendarConfig:
    consent: bool = False
    scope: str = "calendar.readonly"


def disconnect() -> None:
    pass


