"""BigButtons scaffold: primary large action buttons grid."""

from dataclasses import dataclass


@dataclass
class BigButton:
    label: str
    action: str


def default_buttons() -> list[BigButton]:
    return [
        BigButton(label="Weather", action="weather"),
        BigButton(label="Calendar", action="calendar"),
        BigButton(label="Music", action="music"),
        BigButton(label="Photos", action="photos"),
    ]
