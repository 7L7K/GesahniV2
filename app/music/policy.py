from __future__ import annotations

import datetime
from typing import Any


def is_quiet_hours(now: datetime.datetime | None = None, start_hour: int = 22, end_hour: int = 7) -> bool:
    now = now or datetime.datetime.now()
    h = now.hour
    if start_hour <= end_hour:
        return start_hour <= h < end_hour
    return h >= start_hour or h < end_hour


def filter_explicit(content: dict[str, Any]) -> bool:
    # Placeholder: return False if explicit content detected
    return not content.get("explicit", False)


def select_provider(preferred: str | None, available: list[str]) -> str | None:
    if preferred and preferred in available:
        return preferred
    # prefer spotify, then librespot, then ha
    for choice in ("spotify", "librespot", "ha"):
        if choice in available:
            return choice
    return available[0] if available else None


