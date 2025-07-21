import os
import logging
import httpx
import re
from typing import Any, Optional

HOME_ASSISTANT_URL = os.getenv("HOME_ASSISTANT_URL")
HOME_ASSISTANT_TOKEN = os.getenv("HOME_ASSISTANT_TOKEN")

logger = logging.getLogger(__name__)

HEADERS = {
    "Authorization": f"Bearer {HOME_ASSISTANT_TOKEN}",
    "Content-Type": "application/json",
}


async def _request(
    method: str, path: str, json: dict | None = None, timeout: float = 10.0
) -> Any:
    """Internal helper to talk to the Home Assistant API."""
    if not HOME_ASSISTANT_URL or not HOME_ASSISTANT_TOKEN:
        raise RuntimeError("Home Assistant credentials not configured")
    url = f"{HOME_ASSISTANT_URL.rstrip('/')}/api{path}"
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.request(method, url, headers=HEADERS, json=json)
        resp.raise_for_status()
        if resp.content:
            return resp.json()
        return None


async def get_states() -> list[dict]:
    """Return all entity states."""
    data = await _request("GET", "/states")
    return data if isinstance(data, list) else []


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
async def resolve_entity(name: str) -> Optional[str]:
    """Match a user-provided name to an actual Home Assistant entity ID."""
    states = await get_states()
    name_lower = name.lower()
    # exact id or friendly name
    for st in states:
        if st.get("entity_id", "").lower() == name_lower:
            return st["entity_id"]
        friendly = st.get("attributes", {}).get("friendly_name", "")
        if friendly and friendly.lower() == name_lower:
            return st["entity_id"]
    # partial match as fallback
    for st in states:
        if name_lower in st.get("entity_id", "").lower():
            return st["entity_id"]
        friendly = st.get("attributes", {}).get("friendly_name", "").lower()
        if name_lower in friendly:
            return st["entity_id"]
    return None


async def handle_command(prompt: str) -> Optional[str]:
    """Simple intent parser to toggle entities."""
    m = re.match(
        r"^(?:ha[:]?)?\s*(?:turn|switch)\s+(on|off)\s+(.+)$", prompt.strip(), re.I
    )
    if not m:
        return None
    action, name = m.group(1).lower(), m.group(2).strip()
    entity_id = await resolve_entity(name)
    if not entity_id:
        return f"Entity '{name}' not found"
    try:
        if action == "on":
            await turn_on(entity_id)
            return f"Turned on {entity_id}"
        await turn_off(entity_id)
        return f"Turned off {entity_id}"
    except Exception as e:
        logger.exception("Failed to control %s: %s", entity_id, e)
        return "Failed to execute command"
