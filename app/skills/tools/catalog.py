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


