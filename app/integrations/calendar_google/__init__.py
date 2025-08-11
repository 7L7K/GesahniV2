"""Google Calendar consent + cache scaffold."""

from dataclasses import dataclass


@dataclass
class GoogleCalendarConfig:
    consent: bool = False
    scope: str = "https://www.googleapis.com/auth/calendar.readonly"


def disconnect() -> None:
    pass


