"""Calendar connection card scaffold."""

from dataclasses import dataclass


@dataclass
class CalendarCard:
    provider: str | None = None  # e.g., "google", "apple"
    is_connected: bool = False
