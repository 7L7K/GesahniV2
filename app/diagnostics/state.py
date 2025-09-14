from __future__ import annotations

import time
from typing import Literal

_SNAPSHOTS: dict[Literal["before", "after"], dict] = {}
_EVENTS: list[dict] = []
_ROUTER_CALLS: list[dict] = []
_IMPORTS: list[dict] = []


def set_snapshot(phase: Literal["before", "after"], data: dict) -> None:
    _SNAPSHOTS[phase] = data


def get_snapshot(phase: Literal["before", "after"] | None = None) -> dict:
    phase = phase or "after"
    return _SNAPSHOTS.get(phase, {"error": "snapshot-missing", "phase": phase})


def record_event(kind: str, note: str = "") -> None:
    _EVENTS.append({"ts": time.time(), "kind": kind, "note": note})


def events() -> list[dict]:
    return list(_EVENTS)


def record_router_call(where: str, prefix: str | None, routes_total: int) -> None:
    _ROUTER_CALLS.append(
        {
            "ts": time.time(),
            "where": where,
            "prefix": prefix,
            "routes_total": routes_total,
        }
    )


def router_calls() -> list[dict]:
    return list(_ROUTER_CALLS)


def set_import_timings(rows: list[dict]) -> None:
    _IMPORTS.clear()
    _IMPORTS.extend(rows)


def import_timings() -> list[dict]:
    return list(_IMPORTS)
