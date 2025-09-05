from __future__ import annotations
from typing import Dict, List, Literal
import time

_SNAPSHOTS: Dict[Literal["before","after"], dict] = {}
_EVENTS: List[dict] = []
_ROUTER_CALLS: List[dict] = []
_IMPORTS: List[dict] = []

def set_snapshot(phase: Literal["before","after"], data: dict) -> None:
    _SNAPSHOTS[phase] = data

def get_snapshot(phase: Literal["before","after"] | None = None) -> dict:
    phase = phase or "after"
    return _SNAPSHOTS.get(phase, {"error": "snapshot-missing", "phase": phase})

def record_event(kind: str, note: str = "") -> None:
    _EVENTS.append({"ts": time.time(), "kind": kind, "note": note})

def events() -> List[dict]:
    return list(_EVENTS)

def record_router_call(where: str, prefix: str | None, routes_total: int) -> None:
    _ROUTER_CALLS.append({"ts": time.time(), "where": where, "prefix": prefix, "routes_total": routes_total})

def router_calls() -> List[dict]:
    return list(_ROUTER_CALLS)

def set_import_timings(rows: List[dict]) -> None:
    _IMPORTS.clear()
    _IMPORTS.extend(rows)

def import_timings() -> List[dict]:
    return list(_IMPORTS)
