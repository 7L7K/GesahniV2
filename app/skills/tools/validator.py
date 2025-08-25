from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

# Policy defaults
MAX_DURATION_S = 7 * 24 * 3600  # 7 days
MAX_VOLUME_JUMP_PCT = 20
MAX_TEMP = 35
MIN_TEMP = 5
TEMP_CONFIRM_DELTA = 5


def validate_duration(seconds: Optional[int]) -> Tuple[bool, str, bool]:
    """Validate duration seconds.

    Returns (allowed, explanation, requires_confirmation)
    """
    if seconds is None or seconds <= 0:
        return False, "Duration missing or invalid.", False
    if seconds > MAX_DURATION_S:
        return False, f"Duration exceeds maximum of {MAX_DURATION_S} seconds.", True
    return True, "", False


def validate_when(parsed_when: Any) -> Tuple[bool, str, bool]:
    """Ensure 'when' is a concrete datetime (not a recurrence string)."""
    if parsed_when is None:
        return False, "Missing or ambiguous time ('when').", False
    if isinstance(parsed_when, str):
        return False, "Recurring times (e.g. 'every day') are not accepted; please provide a concrete time.", False
    if isinstance(parsed_when, datetime):
        return True, "", False
    return False, "Unsupported 'when' format.", False


def validate_entity_resolution(res: Dict[str, Any]) -> Tuple[bool, str, bool]:
    """Validate resolver output; require disambiguation if ambiguous."""
    if not res:
        return False, "Could not resolve entity.", False
    if res.get("action") == "disambiguate":
        # increment telemetry counter for ambiguous entities
        try:
            from ... import metrics as _metrics

            _metrics.ENTITY_DISAMBIGUATIONS_TOTAL.inc()
        except Exception:
            pass
        # Provide a specific clarifying prompt rather than guessing
        return False, "Which device did you mean? I found multiple matches.", False
    return True, "", False


def validate_level(level: Optional[int]) -> Tuple[bool, str, bool]:
    if level is None:
        return False, "Missing level/brightness.", False
    if not (0 <= level <= 100):
        return False, "Level must be between 0 and 100.", False
    return True, "", False


def validate_temperature(target_temp: Optional[int], current_temp: Optional[int] = None) -> Tuple[bool, str, bool]:
    if target_temp is None:
        return False, "Missing temperature.", False
    if not (MIN_TEMP <= target_temp <= MAX_TEMP):
        return False, f"Temperature must be between {MIN_TEMP} and {MAX_TEMP}°C.", False
    if current_temp is not None and abs(target_temp - current_temp) >= TEMP_CONFIRM_DELTA:
        return False, "Large temperature change requires confirmation.", True
    return True, "", False


def validate_lock_action(action: str) -> Tuple[bool, str, bool]:
    """Locks/unlocks: require confirmation for unlocks by default."""
    if action.lower() == "unlock":
        return False, "Unlocking doors requires explicit confirmation.", True
    return True, "", False

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


