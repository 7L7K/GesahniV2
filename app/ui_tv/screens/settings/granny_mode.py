"""Granny Mode settings scaffold."""

from dataclasses import dataclass


@dataclass
class GrannyModeSettings:
    slow_tts: bool = True
    high_contrast: bool = True
    large_text: bool = True
    do_not_disturb_window: tuple[int, int] | None = None  # start_hour, end_hour
