from __future__ import annotations

import asyncio
import difflib
import logging
import re

from .. import home_assistant as ha
from .base import Skill
from .ledger import record_action

# cache to avoid hitting HA on every call
_LIGHT_MAP: dict[str, str] | None = None
_LIGHT_LOCK = asyncio.Lock()
logger = logging.getLogger(__name__)


async def _build_light_map() -> dict[str, str]:
    """Returns {friendly_name_lower: entity_id} for every light."""
    global _LIGHT_MAP
    async with _LIGHT_LOCK:
        if _LIGHT_MAP is not None:
            return _LIGHT_MAP

        try:
            entities = await ha.get_states()
        except ha.HomeAssistantAPIError as e:
            logger.warning("light map fetch failed: %s", e)
            return {}
        _LIGHT_MAP = {
            e["attributes"].get("friendly_name", e["entity_id"]).lower(): e["entity_id"]
            for e in entities
            if e["entity_id"].startswith("light.")
        }
        return _LIGHT_MAP


def _match_entity(name: str, choices: dict[str, str]) -> str | None:
    name = name.lower().strip()
    if name in choices:
        return choices[name]  # exact

    # fuzzy within ratio≥0.6
    best = difflib.get_close_matches(name, choices.keys(), n=1, cutoff=0.6)
    return choices.get(best[0]) if best else None


async def _friendly_name(entity_id: str) -> str:
    """Return friendly name for entity_id or the id itself if not found."""
    try:
        states = await ha.get_states()
        for s in states:
            if s.get("entity_id") == entity_id:
                return (s.get("attributes") or {}).get("friendly_name", entity_id)
    except Exception:
        pass
    return entity_id


class LightsSkill(Skill):
    PATTERNS = [
        re.compile(
            r"\b(?:turn|switch) (on|off) (?:the )?(?P<name>[\w\s]+?) (?:light|lights|lamp|lamps?)\b",
            re.I,
        ),
        re.compile(
            r"\b(?:set|change) (?:the )?(?P<name>[\w\s]+?) (?:light|lights|lamp|lamps?) to (?P<bright>\d+)%(?:\b|$)",
            re.I,
        ),
    ]

    async def run(self, prompt: str, match: re.Match | None) -> str:
        if match is None:
            return "Sorry, I couldn't match a light command."
        light_map = await _build_light_map()

        if match and "bright" in match.groupdict():  # brightness intent
            name = match.group("name")
            level = int(match.group("bright"))
            level = max(0, min(100, level))
            entity = _match_entity(name, light_map)
            if not entity:
                # Rebuild map once in case cache is stale between tests/sessions
                # Reset the module-level cache safely via name lookup
                globals()["_LIGHT_MAP"] = None
                light_map = await _build_light_map()
                entity = _match_entity(name, light_map)
            if not entity:
                return f"Couldn’t find any light matching “{name}”."
            # guardrails: clamp level and record ledger
            await ha.call_service(
                "light", "turn_on", {"entity_id": entity, "brightness_pct": level}
            )
            friendly = await _friendly_name(entity)
            idemp = f"lights:{entity}:set:{level}:{int(time.time()//10)}"
            await record_action("lights.set", idempotency_key=idemp, metadata={"entity": entity, "level": level}, reversible=True)
            return f"Set {friendly} to {level}% brightness."

        # on/off intent
        action = match.group(1).lower()
        name = match.group("name")
        entity = _match_entity(name, light_map)
        if not entity:
            globals()["_LIGHT_MAP"] = None
            light_map = await _build_light_map()
            entity = _match_entity(name, light_map)
        if not entity:
            return f"Couldn’t find any light matching “{name}”."

        service = "turn_on" if action == "on" else "turn_off"
        await ha.call_service("light", service, {"entity_id": entity})
        friendly = await _friendly_name(entity)
        idemp = f"lights:{entity}:{service}:{int(time.time()//10)}"
        await record_action("lights.toggle", idempotency_key=idemp, metadata={"entity": entity, "service": service}, reversible=True)
        # Natural phrasing
        return f"Turned {action} {friendly}."
