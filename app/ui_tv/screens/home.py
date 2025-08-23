"""Home screen scaffold for the TV UI.

This module defines placeholders for the Home screen state and render contract.
Actual rendering is implemented in the Next.js frontend at `frontend/src/app/tv/page.tsx`.
"""

from dataclasses import dataclass


@dataclass
class HomeScreenModel:
    tile_groups: list[str]
    show_caption_bar: bool = True


def get_default_home_model() -> HomeScreenModel:
    return HomeScreenModel(
        tile_groups=["Weather", "Calendar", "Music", "Photos", "News", "Reminders"]
    )
