"""Simple intent router scaffold."""

from dataclasses import dataclass


@dataclass
class Intent:
    domain: str
    action: str
    entities: dict


def detect_intent(text: str) -> Intent:
    t = text.lower().strip()
    if any(k in t for k in ("weather", "rain", "snow")):
        return Intent(domain="weather", action="get_weather", entities={})
    if any(k in t for k in ("calendar", "appointment", "event")):
        return Intent(domain="calendar", action="list_events", entities={})
    if any(k in t for k in ("music", "song", "play")):
        return Intent(domain="music", action="play", entities={})
    if any(k in t for k in ("photo", "album", "pictures")):
        return Intent(domain="photos", action="show", entities={})
    if any(k in t for k in ("remind", "reminder")):
        return Intent(domain="reminders", action="add", entities={})
    if any(k in t for k in ("news", "headline")):
        return Intent(domain="news", action="read", entities={})
    if any(k in t for k in ("recipe", "cook", "how to")):
        return Intent(domain="recipes", action="show", entities={})
    if any(k in t for k in ("help", "emergency", "scam")):
        return Intent(domain="safety", action="assist", entities={})
    return Intent(domain="smalltalk", action="chat", entities={})
