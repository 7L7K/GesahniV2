import os
import logging
import re
import json as json_module
from dataclasses import dataclass
from typing import Any, List, Optional

from .http_utils import json_request, log_exceptions

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
# Default headers; add Authorization if we actually have a token
HEADERS: dict[str, str] = {"Content-Type": "application/json"}
if HOME_ASSISTANT_TOKEN:
    HEADERS["Authorization"] = f"Bearer {HOME_ASSISTANT_TOKEN}"

# Room‑name synonyms so users can say “lounge” and we map → living room
ROOM_SYNONYMS = {
    "living room": ["lounge", "den"],
    "kitchen": ["cook room"],
}
_SYN_TO_ROOM = {syn: room for room, syns in ROOM_SYNONYMS.items() for syn in syns}


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
        headers=HEADERS,
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
    """Return all HA entity states or raise ``HomeAssistantAPIError``."""
    try:
        data = await _request("GET", "/states")
    except Exception as e:  # pragma: no cover - network layer
        logger.warning("Failed to fetch states: %s", e)
        raise HomeAssistantAPIError(str(e)) from e

    if not isinstance(data, list):
        raise HomeAssistantAPIError("invalid_response")
    return data


async def call_service(domain: str, service: str, data: dict) -> Any:
    """Call an HA service and pipe basic telemetry into the log record var."""
    rec = log_record_var.get()
    if rec is not None:
        rec.ha_service_called = f"{domain}.{service}"
        ids = data.get("entity_id")
        if ids is not None:
            rec.entity_ids = [ids] if isinstance(ids, str) else list(ids)
    return await _request("POST", f"/services/{domain}/{service}", json=data)


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
    """Return entity IDs that match the given name or its synonyms."""
    try:
        states = await get_states()
    except HomeAssistantAPIError as e:
        logger.warning("resolve_entity failed: %s", e)
        return []
    target = _SYN_TO_ROOM.get(name.lower(), name.lower())

    # exact match first
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if target == eid.lower() or target == friendly.lower():
            return [eid]

    # substring fallback
    matches: List[str] = []
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if target in eid.lower() or target in friendly.lower():
            matches.append(eid)
    return matches


async def handle_command(prompt: str) -> Optional[CommandResult]:
    """Parse simple "ha: turn on X" commands and execute them."""
    m = re.match(
        r"^(?:ha[:]?)?\s*(?:turn|switch)\s+(on|off)\s+(.+)$", prompt.strip(), re.I
    )
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
