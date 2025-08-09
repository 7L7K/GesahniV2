import os
import logging
import re
import time
import json as json_module
from dataclasses import dataclass
from typing import Any, List, Optional

from .http_utils import json_request, log_exceptions
from . import alias_store

from .telemetry import log_record_var

# ---------------------------------------------------------------------------
# Environment & Defaults
# ---------------------------------------------------------------------------
# Use localhost by default so the module can import even if the env var is
# missing. 8123 is the standard HA port.
HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL", "http://localhost:8123")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _headers() -> dict[str, str]:
    """Build request headers using the current token."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if HOME_ASSISTANT_TOKEN:
        headers["Authorization"] = f"Bearer {HOME_ASSISTANT_TOKEN}"
    return headers


# Room‑name synonyms so users can say “lounge” and we map → living room
ROOM_SYNONYMS = {
    "living room": ["lounge", "den", "livingroom"],
    "kitchen": ["cook room"],
    "bedroom": ["master", "primary"],
}
_SYN_TO_ROOM = {
    **{room: room for room in ROOM_SYNONYMS},
    **{syn: room for room, syns in ROOM_SYNONYMS.items() for syn in syns},
}

# Cache for /states results so resolve_entity doesn't spam the API.
_STATES_CACHE: list[dict] | None = None
_STATES_CACHE_EXP: float = 0.0
_STATES_TTL = 1.0  # seconds


@dataclass(slots=True)
class CommandResult:
    success: bool
    message: str
    data: dict | None = None


class HomeAssistantAPIError(Exception):
    """Raised when a Home Assistant API call fails."""


def _redact(obj: Any) -> Any:
    """Recursively replace any access_token values with [redacted]."""
    if isinstance(obj, dict):
        return {
            k: ("[redacted]" if k == "access_token" else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


@log_exceptions("home_assistant")
async def _request(
    method: str, path: str, json: dict | None = None, timeout: float = 10.0
) -> Any:
    """Low‑level Home Assistant request helper with rich logging."""
    url = f"{HOME_ASSISTANT_URL.rstrip('/')}/api{path}"
    logger.info(
        "ha_request", extra={"meta": {"method": method, "path": path, "json": json}}
    )
    data, error = await json_request(
        method,
        url,
        headers=_headers(),
        json=json,
        timeout=timeout,
    )

    body = json_module.dumps(_redact(data)) if not error else error
    if len(body) > 2048:
        body = body[:2048] + "..."
    logger.info(
        "ha_response",
        extra={"meta": {"status": 200 if not error else "err", "body": body}},
    )

    if error:
        raise RuntimeError(error)
    return data


# ---------------------------------------------------------------------------
# Public API helpers
# ---------------------------------------------------------------------------
async def get_states() -> list[dict]:
    """Return all HA entity states with a short lived cache."""
    global _STATES_CACHE, _STATES_CACHE_EXP
    now = time.monotonic()
    if _STATES_CACHE is not None and now < _STATES_CACHE_EXP:
        return _STATES_CACHE
    try:
        data = await _request("GET", "/states")
        _STATES_CACHE = data if isinstance(data, list) else []
        _STATES_CACHE_EXP = now + _STATES_TTL
    except Exception as e:
        logger.warning(
            "Failed to fetch states: %s (last cache exp: %.2f, now: %.2f)",
            e,
            _STATES_CACHE_EXP,
            now,
        )
        _STATES_CACHE = []
        _STATES_CACHE_EXP = 0.0
    return _STATES_CACHE


def invalidate_states_cache() -> None:
    """Clear cached HA states."""
    global _STATES_CACHE, _STATES_CACHE_EXP
    _STATES_CACHE = None
    _STATES_CACHE_EXP = 0.0


async def call_service(domain: str, service: str, data: dict) -> Any:
    """Call an HA service and pipe basic telemetry into the log record var."""
    rec = log_record_var.get()
    if rec is not None:
        rec.ha_service_called = f"{domain}.{service}"
        ids = data.get("entity_id")
        if ids is not None:
            rec.entity_ids = [ids] if isinstance(ids, str) else list(ids)
    result = await _request("POST", f"/services/{domain}/{service}", json=data)
    invalidate_states_cache()
    return result


async def turn_on(entity_id: str) -> Any:
    domain = entity_id.split(".")[0]
    return await call_service(domain, "turn_on", {"entity_id": entity_id})


async def turn_off(entity_id: str) -> Any:
    domain = entity_id.split(".")[0]
    return await call_service(domain, "turn_off", {"entity_id": entity_id})


# ---------------------------------------------------------------------------
# Startup & Health Check
# ---------------------------------------------------------------------------
async def startup_check() -> None:
    """Verify HA connectivity, but never crash the whole app."""
    if not HOME_ASSISTANT_TOKEN:
        logger.warning("HA startup skipped – missing HOME_ASSISTANT_TOKEN env var")
        return

    try:
        await _request("GET", "/states")
        logger.info("Connected to Home Assistant successfully")
    except Exception as e:
        logger.warning("Home Assistant unreachable: %s", e)


# ---------------------------------------------------------------------------
# Prompt‑style command parser (very lightweight)
# ---------------------------------------------------------------------------
async def resolve_entity(name: str) -> List[str]:
    """Return entity IDs that match the given name, alias, or its synonyms.

    Resolution order:
    1) Exact alias match from alias_store (user-taught nicknames)
    2) Exact match on entity_id or friendly_name (case-insensitive)
    3) Synonym/room normalization then exact match
    4) Substring fallback on entity_id/friendly_name
    5) Domain plural to domain mapping (e.g. "lights" -> domain "light.*")
    """
    normalized = name.strip().lower()
    try:
        # Check saved aliases first
        alias = await alias_store.get(normalized)
        if alias:
            return [alias]
    except Exception as e:
        logger.debug("alias lookup failed: %s", e)

    try:
        states = await get_states()
    except HomeAssistantAPIError as e:
        logger.warning("resolve_entity failed: %s", e)
        return []

    # 2) Exact entity_id or friendly_name match
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if normalized == eid.lower() or normalized == friendly.lower():
            return [eid]

    # 3) Synonym normalization then exact match
    target = _SYN_TO_ROOM.get(normalized, normalized)
    if target != normalized:
        for st in states:
            eid = st.get("entity_id", "")
            friendly = st.get("attributes", {}).get("friendly_name", "")
            if target == eid.lower() or target == friendly.lower():
                return [eid]

    # 4) Substring fallback
    matches: List[str] = []
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if target in eid.lower() or target in friendly.lower():
            matches.append(eid)

    # 5) Domain collection resolution (e.g., "lights" -> all light entities)
    if not matches:
        plural_to_domain = {
            "lights": "light",
            "switches": "switch",
            "fans": "fan",
            "covers": "cover",
            "scripts": "script",
            "scenes": "scene",
        }
        domain = plural_to_domain.get(target)
        if domain:
            matches = [st.get("entity_id", "") for st in states if st.get("entity_id", "").startswith(domain + ".")]

    return [m for m in matches if m]


async def handle_command(prompt: str) -> Optional[CommandResult]:
    """Parse HA control commands and execute them.

    Supports:
      - "turn on/off <name>"
      - "toggle <name>"
      - "set <name> brightness <0-100>" (lights)
    """
    text = prompt.strip()
    # toggle
    m = re.match(r"^(?:ha[:]?)?\s*toggle\s+(.+)$", text, re.I)
    if m:
        name = m.group(1).strip()
        entities = await resolve_entity(name)
        if not entities:
            return CommandResult(False, "entity_not_found", {"name": name})
        if len(entities) > 1:
            return CommandResult(False, "confirm_required", {"entities": entities})
        eid = entities[0]
        domain = eid.split(".")[0]
        try:
            await call_service(domain, "toggle", {"entity_id": eid})
            return CommandResult(True, f"Toggled {eid}")
        except Exception as e:
            logger.exception("Failed to toggle %s: %s", eid, e)
            return CommandResult(False, "command_failed")

    # set brightness
    m = re.match(
        r"^(?:ha[:]?)?\s*set\s+(.+?)\s+brightness\s+(\d{1,3})\s*%?$",
        text,
        re.I,
    )
    if m:
        name, bright_str = m.group(1).strip(), m.group(2)
        level = max(0, min(100, int(bright_str)))
        entities = await resolve_entity(name)
        if not entities:
            return CommandResult(False, "entity_not_found", {"name": name})
        if len(entities) > 1:
            return CommandResult(False, "confirm_required", {"entities": entities})
        eid = entities[0]
        try:
            await call_service("light", "turn_on", {"entity_id": eid, "brightness_pct": level})
            return CommandResult(True, f"Set {eid} brightness to {level}%")
        except Exception as e:
            logger.exception("Failed to set brightness for %s: %s", eid, e)
            return CommandResult(False, "command_failed")

    # turn on/off
    m = re.match(r"^(?:ha[:]?)?\s*(?:turn|switch)\s+(on|off)\s+(.+)$", text, re.I)
    if not m:
        return None
    action, name = m.group(1).lower(), m.group(2).strip()
    entities = await resolve_entity(name)
    if not entities:
        return CommandResult(False, "entity_not_found", {"name": name})
    if len(entities) > 1:
        return CommandResult(False, "confirm_required", {"entities": entities})

    entity_id = entities[0]
    try:
        if action == "on":
            await turn_on(entity_id)
            return CommandResult(True, f"Turned on {entity_id}")
        await turn_off(entity_id)
        return CommandResult(True, f"Turned off {entity_id}")
    except Exception as e:
        logger.exception("Failed to control %s: %s", entity_id, e)
        return CommandResult(False, "command_failed")
