"""Compatibility wrappers exposing calendar functions for top-level aliases.

These wrappers call the canonical calendar router implementations in
`app.api.calendar` and adapt their return values to the lightweight shapes
expected by the alias router (dicts/lists rather than Pydantic models).
"""

from __future__ import annotations

from typing import Any

from app.api import calendar as _calendar_api


async def _to_list_of_dicts(items: list) -> list[dict]:
    out: list[dict] = []
    for it in items or []:
        if hasattr(it, "model_dump"):
            out.append(it.model_dump())
        elif hasattr(it, "dict"):
            out.append(it.dict())
        else:
            out.append(dict(it) if isinstance(it, dict) else {"value": it})
    return out


async def list_events() -> dict[str, Any]:
    """Return a normalized shape for top-level `/calendar/list` alias.

    Shape: {"events": [...items...]}
    """
    try:
        res = await _calendar_api.list_all()
        items = await _to_list_of_dicts(getattr(res, "items", []))
        return {"events": items}
    except Exception:
        return {"events": []}


async def next_event() -> dict[str, Any]:
    """Return a normalized shape for top-level `/calendar/next` alias.

    Shape: {"event": item | None, "detail": ...}
    """
    try:
        res = await _calendar_api.next_three()
        items = await _to_list_of_dicts(getattr(res, "items", []))
        if not items:
            return {"event": None, "detail": "no_upcoming_events"}
        return {"event": items[0]}
    except Exception:
        return {"event": None, "detail": "no_upcoming_events"}


async def todays_events() -> dict[str, Any]:
    """Return a normalized shape for top-level `/calendar/today` alias.

    Shape: {"events": [...items...]}
    """
    try:
        res = await _calendar_api.list_today()
        items = await _to_list_of_dicts(getattr(res, "items", []))
        return {"events": items}
    except Exception:
        return {"events": []}
