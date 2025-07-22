import os
import logging
import httpx
import re
from typing import Any, Optional, List
from .logging_config import configure_logging

configure_logging()

HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")
if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
    raise RuntimeError("Home Assistant credentials not configured")

logger = logging.getLogger(__name__)

HEADERS = {
    "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
    "Content-Type": "application/json",
}

ROOM_SYNONYMS = {
    "living room": ["lounge", "family room"],
    "kitchen": ["cooking area"],
}


async def _request(
    method: str, path: str, json: dict | None = None, timeout: float = 10.0
) -> Any:
    """Internal helper to talk to the Home Assistant API."""
    logger.info("ha_request", extra={"meta": {"method": method, "path": path, "json": json}})
    url = f"{HOME_ASSISTANT_URL.rstrip('/')}/api{path}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, headers=HEADERS, json=json)
        resp.raise_for_status()
        data = resp.json() if resp.content else None
        logger.info("ha_response", extra={"meta": {"status": resp.status_code, "data": data}})
        return data


async def get_states() -> list[dict]:
    """Return all entity states."""
    data = await _request("GET", "/states")
    return data if isinstance(data, list) else []

async def verify_connection() -> None:
    await get_states()


async def call_service(domain: str, service: str, data: dict) -> Any:
    """Call a Home Assistant service."""
    return await _request("POST", f"/services/{domain}/{service}", json=data)


async def turn_on(entity_id: str) -> Any:
    domain = entity_id.split(".")[0]
    return await call_service(domain, "turn_on", {"entity_id": entity_id})


async def turn_off(entity_id: str) -> Any:
    domain = entity_id.split(".")[0]
    return await call_service(domain, "turn_off", {"entity_id": entity_id})


# ---------------------------------------------------------------------------
# Dynamic entity resolution (line 78)
# ---------------------------------------------------------------------------
def _normalize_name(name: str) -> str:
    lower = name.lower()
    for room, syns in ROOM_SYNONYMS.items():
        if lower == room or lower in syns:
            return room
    return name

async def resolve_entities(name: str) -> List[str]:
    states = await get_states()
    name_lower = _normalize_name(name).lower()
    matches = []
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if eid.lower() == name_lower or friendly.lower() == name_lower:
            matches.append(eid)
    for st in states:
        eid = st.get("entity_id", "")
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if name_lower in eid.lower() or name_lower in friendly.lower():
            matches.append(eid)
    return list(dict.fromkeys(matches))


async def handle_command(prompt: str) -> Optional[str | dict]:
    m = re.match(
        r"^(?:ha[:]?)?\s*(?:turn|switch)\s+(on|off)\s+(.+)$", prompt.strip(), re.I
    )
    if not m:
        return None
    action, name = m.group(1).lower(), m.group(2).strip()
    entities = await resolve_entities(name)
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
