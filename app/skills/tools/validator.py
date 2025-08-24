"""
Validation policy for tool slot shapes (design-only).

This module documents validation rules for tool slots. Implementations should
use these rules to accept or reject tool outputs from the LLM.

Rules (human-readable):

- Duration (duration_s): must be integer seconds, 5 <= duration_s <= 86400.
- When (when): must resolve to an ISO8601 datetime or a cron/schedule rule
  that the system recognizes. When must be concrete for one-off reminders.
- Entity resolution: must return a single canonical entity_id. If multiple
  matches exist, validation fails and system should ask for clarification.
- Level/volume: must be integer 0..100. If LLM suggests relative changes
  (e.g., +30%), the validator translates to absolute target and enforces
  the safety policy (no >20% jumps without confirmation).
- Slots required: If a required slot is missing, reject and ask for the
  missing slot rather than guessing.

Validator API (suggested):

def validate(tool_name: str, slots: dict) -> tuple[bool, list[str], dict]
    - Returns (ok, errors, normalized_slots)

Fallback behaviors:
- If missing required slot: request clarification.
- If entity ambiguous: return list of candidates for follow-up.
- If numeric out-of-range: clamp only when safe and inform user; else ask.

"""


