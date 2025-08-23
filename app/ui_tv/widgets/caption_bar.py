"""Caption bar scaffold: "You said: …"""

from dataclasses import dataclass


@dataclass
class CaptionBarModel:
    transcript: str | None
    is_visible: bool = True
