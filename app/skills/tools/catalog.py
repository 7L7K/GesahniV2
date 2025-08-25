from __future__ import annotations

from typing import Any, Dict, Tuple

from ... import home_assistant as ha
from ..tools import validator


# Minimal tool catalog mirroring Tier-0 slots
TOOL_CATALOG: Dict[str, Dict[str, Any]] = {
    "timer.start": {
        "slots": {"label": str, "duration_s": int},
        "reversible": True,
    },
    "reminder.set": {
        "slots": {"task": str, "when": (str, "datetime")},
        "reversible": True,
    },
    "light.set_brightness": {
        "slots": {"entity": str, "brightness_pct": int},
        "reversible": True,
    },
    "media.play": {
        "slots": {"entity": str, "uri": str},
        "reversible": True,
    },
}


async def validate_and_execute(tool: str, slots: Dict[str, Any], user_id: str | None = None) -> Tuple[bool, str, bool]:
    """Validate tool slots and execute the action.

    Returns (executed, message, requires_confirmation).
    """
    if tool not in TOOL_CATALOG:
        return False, f"Unknown tool {tool}", False

    # Timer
    if tool == "timer.start":
        dur = slots.get("duration_s")
        ok, expl, confirm = validator.validate_duration(dur)
        if not ok:
            return False, expl, confirm
        label = slots.get("label") or "gesahni"
        # call HA timer service
        try:
            await ha.call_service("timer", "start", {"entity_id": f"timer.{label}", "duration": f"00:00:{int(dur)}"})
            return True, f"Timer {label} started for {dur} seconds.", False
        except Exception as e:
            return False, f"Failed to start timer: {e}", False

    # Reminder
    if tool == "reminder.set":
        when = slots.get("when")
        ok, expl, confirm = validator.validate_when(when)
        if not ok:
            return False, expl, confirm
        task = slots.get("task")
        # persist in reminders (best-effort) - use scheduler in skill layer
        try:
            # convert when to ISO if datetime-like
            when_iso = when.isoformat() if hasattr(when, "isoformat") else str(when)
            await ha.call_service("notify", "persistent_notification", {"message": f"Reminder: {task} at {when_iso}"})
            return True, f"Reminder set for {task} at {when_iso}.", False
        except Exception as e:
            return False, f"Failed to set reminder: {e}", False

    # Lights
    if tool == "light.set_brightness":
        entity = slots.get("entity")
        level = slots.get("brightness_pct")
        res_ok, expl, confirm = validator.validate_entity_resolution({"entity_id": entity, "friendly_name": entity, "confidence": 1.0})
        if not res_ok:
            return False, expl, confirm
        ok, expl, confirm = validator.validate_level(level)
        if not ok:
            return False, expl, confirm
        try:
            await ha.call_service("light", "turn_on", {"entity_id": entity, "brightness_pct": level})
            return True, f"Set {entity} to {level}%", False
        except Exception as e:
            return False, f"Failed to set brightness: {e}", False

    # Media (play)
    if tool == "media.play":
        entity = slots.get("entity")
        uri = slots.get("uri")
        if not entity or not uri:
            return False, "Missing entity or uri for media.play", False
        try:
            await ha.call_service("media_player", "play_media", {"entity_id": entity, "media_content_id": uri, "media_content_type": "music"})
            return True, f"Playing media on {entity}", False
        except Exception as e:
            return False, f"Failed to play media: {e}", False

    return False, "Tool not implemented", False

"""
Tools catalog (design-only): map tool names to slot shapes.

This file contains descriptive tool definitions (shapes only) used by the
LLM fallback path. It is intentionally non-executable documentation that
describes the schema for each tool.

Example entry format (fields only):
 - name: string identifier of the tool
 - slots: dict of slot_name -> type/description
 - required: list of required slot names
 - description: short human-readable description

"""

TOOLS = [
    {
        "name": "set_timer",
        "slots": {
            "duration_s": "int (seconds, between 5 and 86400)",
            "label": "string (optional, single token)",
        },
        "required": ["duration_s"],
        "description": "Start a named timer for duration_s seconds",
    },
    {
        "name": "set_reminder",
        "slots": {
            "when": "ISO8601 datetime or schedule rule",
            "text": "string",
        },
        "required": ["when", "text"],
        "description": "Schedule a one-off reminder",
    },
    {
        "name": "set_light",
        "slots": {"entity_id": "string (canonical)", "action": "on|off|set", "level": "int 0..100 (optional)"},
        "required": ["entity_id", "action"],
        "description": "Control a light or set brightness",
    },
    {
        "name": "play_media",
        "slots": {"device": "string (optional)", "action": "play|pause|stop", "target": "string (optional)"},
        "required": ["action"],
        "description": "Control media playback",
    },
]


