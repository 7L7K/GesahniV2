from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.security import verify_token

# Public-by-default in tests; gate auth via CALENDAR_PUBLIC
CAL_PUBLIC = os.getenv("CALENDAR_PUBLIC", "1").strip().lower() in {"1", "true", "yes", "on"}
_DEPS = [] if CAL_PUBLIC else [Depends(verify_token)]
router = APIRouter(tags=["Calendar"], dependencies=_DEPS)


# Note: The calendar file path is resolved dynamically in _read() so tests that
#       monkeypatch CALENDAR_FILE after import see updated data.
CALENDAR_FILE = Path(os.getenv("CALENDAR_FILE", "data/calendar.json"))


def _read() -> list[dict]:
    try:
        path = Path(os.getenv("CALENDAR_FILE", str(CALENDAR_FILE)))
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8") or "[]")
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


class Event(BaseModel):
    date: str
    time: str | None = None
    title: str | None = None
    description: str | None = None
    location: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "date": "2025-08-12",
                "time": "09:30",
                "title": "Doctor appointment",
                "description": "Annual checkup",
                "location": "Clinic",
            }
        }
    )


class EventsResponse(BaseModel):
    items: list[Event]

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "items": [
                    {
                        "date": "2025-08-12",
                        "time": "09:30",
                        "title": "Doctor appointment",
                        "description": "Annual checkup",
                        "location": "Clinic",
                    }
                ]
            }
        }
    )


def _sort_key(e: dict) -> tuple[str, str]:
    return (str(e.get("date") or ""), str(e.get("time") or ""))

# OpenAPI examples -------------------------------------------------------------
EXAMPLE_TODAY = {
    "items": [
        {"date": "2025-08-12", "time": "09:30", "title": "Doctor appointment", "location": "Clinic"},
        {"date": "2025-08-12", "time": "13:00", "title": "Lunch with Sam", "location": "Cafe"},
    ]
}

EXAMPLE_LIST = {
    "items": [
        {"date": "2025-08-12", "time": "09:30", "title": "Doctor appointment"},
        {"date": "2025-08-13", "time": "10:00", "title": "Grocery pickup"},
    ]
}

EXAMPLE_NEXT = {
    "items": [
        {"date": "2025-08-12", "time": "09:30", "title": "Doctor appointment"},
    ]
}


@router.get(
    "/calendar/today",
    response_model=EventsResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": EXAMPLE_TODAY,
                }
            }
        }
    },
)
async def list_today() -> EventsResponse:
    today = os.getenv("PYTEST_FAKE_TODAY") or _dt.date.today().isoformat()
    items = [e for e in _read() if str(e.get("date") or "") == today]
    items.sort(key=_sort_key)
    return EventsResponse(items=[Event(**it) for it in items])


@router.get(
    "/calendar/next",
    response_model=EventsResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": EXAMPLE_NEXT,
                }
            }
        }
    },
)
async def next_three() -> EventsResponse:
    # Prefer fake provider backing (Detroit TZ), fall back to local JSON
    try:
        from app.integrations.calendar_fake import FakeCalendarProvider

        provider = FakeCalendarProvider()
        ev = provider.list_next(3)
        if ev:  # Only use provider when it yields events
            items = [
                {
                    "date": e.get("start_local", "").split("T")[0],
                    "time": e.get("start_local", "").split("T")[1][:5] if "T" in (e.get("start_local") or "") else None,
                    "title": e.get("title"),
                }
                for e in ev
            ]
            return EventsResponse(items=[Event(**it) for it in items])
    except Exception:
        pass
    # Fallback to local JSON data
    today = os.getenv("PYTEST_FAKE_TODAY") or _dt.date.today().isoformat()
    items = [e for e in _read() if (str(e.get("date") or "")) >= today]
    items.sort(key=_sort_key)
    return EventsResponse(items=[Event(**it) for it in items[:3]])


@router.get("/tv/calendar/next", include_in_schema=False)
async def tv_calendar_next_alias() -> EventsResponse:
    """Alias for TV surfaces expecting /tv/calendar/next.

    Mirrors /calendar/next without duplicating logic; hidden from OpenAPI to
    avoid drift in documented surface.
    """
    return await next_three()


@router.get(
    "/calendar/list",
    response_model=EventsResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": EXAMPLE_LIST,
                }
            }
        }
    },
)
async def list_all() -> EventsResponse:
    items = list(_read())
    items.sort(key=_sort_key)
    return EventsResponse(items=[Event(**it) for it in items])


