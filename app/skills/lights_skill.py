from __future__ import annotations
import re, asyncio, difflib
from .base import Skill
from .. import home_assistant as ha

# cache to avoid hitting HA on every call
_LIGHT_MAP: dict[str, str] | None = None
_LIGHT_LOCK = asyncio.Lock()

async def _build_light_map() -> dict[str, str]:
    """Returns {friendly_name_lower: entity_id} for every light."""
    global _LIGHT_MAP
    async with _LIGHT_LOCK:
        if _LIGHT_MAP is not None:
            return _LIGHT_MAP

        entities = await ha.get_states()
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

class LightsSkill(Skill):
    PATTERNS = [
        re.compile(r"\bturn (on|off) (the )?(?P<name>[\w\s]+?) lights?\b", re.I),
        re.compile(r"\bset (the )?(?P<name>[\w\s]+?) lights? to (?P<bright>\d+)%\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        light_map = await _build_light_map()

        if "bright" in match.groupdict():            # brightness intent
            name = match.group("name")
            level = int(match.group("bright"))
            entity = _match_entity(name, light_map)
            if not entity:
                return f"Couldn’t find any light matching “{name}”."
            await ha.call_service("light", "turn_on",
                                   {"entity_id": entity, "brightness_pct": level})
            return f"Set {name.title()} to {level}% brightness."

        # on/off intent
        action = match.group(1).lower()
        name   = match.group("name")
        entity = _match_entity(name, light_map)
        if not entity:
            return f"Couldn’t find any light matching “{name}”."

        service = "turn_on" if action == "on" else "turn_off"
        await ha.call_service("light", service, {"entity_id": entity})
        return f"{action.title()}ed {name.title()} lights."
