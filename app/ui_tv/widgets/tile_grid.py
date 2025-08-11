"""TileGrid scaffold."""

from dataclasses import dataclass


@dataclass
class Tile:
    title: str
    subtitle: str | None = None


def empty_grid() -> list[Tile]:
    return []


