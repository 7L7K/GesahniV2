from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict, Literal, Optional

ServiceName = Literal["gmail", "calendar"]
ServiceStatus = Literal["enabled", "disabled", "error"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse(service_state: Optional[str]) -> Dict[str, dict]:
    if not service_state:
        return {}
    try:
        data = json.loads(service_state)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def serialize(state: Dict[str, dict]) -> str:
    return json.dumps(state, separators=(",", ":"))


def _ensure_entry(st: Dict[str, dict], service: ServiceName) -> dict:
    entry = st.get(service) or {}
    entry.setdefault("status", "disabled")
    entry.setdefault("last_changed_at", _now_iso())
    if "last_error" not in entry:
        entry["last_error"] = None
    return entry


def set_service_enabled(service_state: Optional[str], service: ServiceName, enabled: bool) -> str:
    st = parse(service_state)
    entry = _ensure_entry(st, service)
    entry["status"] = "enabled" if enabled else "disabled"
    entry["last_changed_at"] = _now_iso()
    if not enabled:
        entry["last_error"] = None
    st[service] = entry
    return serialize(st)


def set_service_error(service_state: Optional[str], service: ServiceName, code: str) -> str:
    st = parse(service_state)
    entry = _ensure_entry(st, service)
    entry["status"] = "error"
    entry["last_changed_at"] = _now_iso()
    entry["last_error"] = {"code": code, "at": _now_iso()}
    st[service] = entry
    return serialize(st)


# Backwards-compatible alias used elsewhere in the codebase
def set_status(service_state: Optional[str], service: ServiceName, status: ServiceStatus, *, last_error_code: Optional[str] = None) -> str:
    if status == "enabled":
        return set_service_enabled(service_state, service, True)
    if status == "disabled":
        return set_service_enabled(service_state, service, False)
    if status == "error":
        return set_service_error(service_state, service, last_error_code or "error")
    return serialize(parse(service_state))


def get_status(service_state: Optional[str], service: ServiceName) -> Optional[ServiceStatus]:
    st = parse(service_state)
    entry = st.get(service)
    return entry.get("status") if isinstance(entry, dict) else None

