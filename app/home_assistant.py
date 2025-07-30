import os
import logging
import httpx
import re
from typing import Any, List, Optional

from .telemetry import log_record_var

HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")

if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
    raise RuntimeError("Missing Home Assistant credentials")

logger = logging.getLogger(__name__)

HEADERS = {
    "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
    "Content-Type": "application/json",
}

ROOM_SYNONYMS = {
    "living room": ["lounge", "den"],
    "kitchen": ["cook room"],
}

_SYN_TO_ROOM = {syn: room for room, syns in ROOM_SYNONYMS.items() for syn in syns}


async def _request(method: str, path: str, json: dict | None = None, timeout: float = 10.0) -> Any:
    """Internal helper to talk to the Home Assistant API."""
    url = f"{HOME_ASSISTANT_URL.rstrip('/')}/api{path}"
    logger.info("ha_request", extra={"meta": {"method": method, "path": path, "json": json}})
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, headers=HEADERS, json=json)
    logger.info("ha_response", extra={"meta": {"status": resp.status_code, "body": resp.text}})
    resp.raise_for_status()
    return resp.json() if resp.content else None


async def get_states() -> list[dict]:
    """Return all entity states."""
    data = await _request("GET", "/states")
    return data if isinstance(data, list) else []


async def call_service(domain: str, service: str, data: dict) -> Any:
    """Call a Home Assistant service and record telemetry."""
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


async def startup_check() -> None:
    if HOME_ASSISTANT_URL:
        await _request("GET", "/states")
    else:
        logger.warning("Skipping HA startup check – no URL provided")


# ---------------------------------------------------------------------------
# Dynamic entity resolution (line 78)
# ---------------------------------------------------------------------------
async def resolve_entity(name: str) -> List[str]:
    """Return matching entity IDs for the given name, considering synonyms."""
    states = await get_states()
    target = _SYN_TO_ROOM.get(name.lower(), name.lower())
    matches: List[str] = []
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if target == eid.lower() or target == friendly.lower():
            return [eid]
        if target in eid.lower() or target in friendly.lower():
            matches.append(eid)
    return matches


async def handle_command(prompt: str) -> Optional[Any]:
    """Parse simple HA commands and execute them."""
    m = re.match(
        r"^(?:ha[:]?)?\s*(?:turn|switch)\s+(on|off)\s+(.+)$", prompt.strip(), re.I
    )
    if not m:
        return None
    action, name = m.group(1).lower(), m.group(2).strip()
    entities = await resolve_entity(name)
    if not entities:
        return {"error": "entity_not_found", "name": name}
    if len(entities) > 1:
        return {"confirm_required": True, "entities": entities}
    entity_id = entities[0]
    try:
        if action == "on":
            await turn_on(entity_id)
            return f"Turned on {entity_id}"
        await turn_off(entity_id)
        return f"Turned off {entity_id}"
    except Exception as e:
        logger.exception("Failed to control %s: %s", entity_id, e)
        return "Failed to execute command"
