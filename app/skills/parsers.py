from __future__ import annotations

import difflib
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .. import home_assistant as ha


def parse_duration(amount: Optional[str], unit: Optional[str]) -> Optional[int]:
    """Parse an amount+unit into seconds (int) or return None.

    Canonical output: seconds (int)
    """
    if not amount:
        return None
    try:
        n = int(amount)
    except Exception:
        return None
    u = (unit or "").lower()
    if u.startswith("sec"):
        return n
    if u.startswith("min"):
        return n * 60
    if u.startswith("hr") or u.startswith("hour"):
        return n * 3600
    # fallback: treat as seconds
    return n


def parse_level(level_str: Optional[str]) -> Optional[int]:
    """Normalize a brightness/level string to 0-100 int.

    Canonical output: int in 0-100
    """
    if level_str is None:
        return None
    try:
        v = int(level_str)
    except Exception:
        m = re.search(r"(\d+)", level_str or "")
        if not m:
            return None
        v = int(m.group(1))
    return max(0, min(100, v))


def parse_when(when_str: Optional[str]) -> Optional[Any]:
    """Parse human-friendly when expressions.

    Canonical outputs:
      - timezone-aware datetime (datetime) for a single date/time
      - recurrence rule string (e.g. "every day") when repeating

    Conservative: when ambiguous, return None.
    """
    if not when_str:
        return None
    s = when_str.strip().lower()
    now = datetime.now(timezone.utc)
    m = re.match(r"in\s+(?P<n>\d+)\s*(?P<unit>seconds?|minutes?|hours?|hrs?|mins?)", s)
    if m:
        n = int(m.group("n"))
        u = m.group("unit")
        if u.startswith("sec"):
            return now + timedelta(seconds=n)
        if u.startswith("min"):
            return now + timedelta(minutes=n)
        return now + timedelta(hours=n)

    m = re.match(r"tomorrow(?: at )?(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ampm>am|pm)?", s)
    if m:
        dt = now + timedelta(days=1)
        hr = int(m.group("h"))
        mn = int(m.group("m") or 0)
        ampm = m.group("ampm")
        if ampm:
            if ampm == "pm" and hr < 12:
                hr += 12
            if ampm == "am" and hr == 12:
                hr = 0
        return datetime(dt.year, dt.month, dt.day, hr, mn, tzinfo=timezone.utc)

    m = re.match(r"every\s+(?P<period>day|week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)", s)
    if m:
        return f"every {m.group('period')}"

    return None


async def resolve_entity(name: str, kind: str = "light") -> Dict[str, Any]:
    """Resolve a friendly name to a single entity id and confidence.

    Canonical output: {entity_id, friendly_name, confidence}

    If ambiguous, return {"action": "disambiguate", "candidates": [...]}
    """
    name_norm = (name or "").strip().lower()
    if not name_norm:
        return {"action": "disambiguate", "candidates": []}

    try:
        states = await ha.get_states()
    except Exception:
        states = []

    choices: Dict[str, str] = {}
    for s in states:
        eid = s.get("entity_id")
        if not eid:
            continue
        if kind and not eid.startswith(f"{kind}."):
            continue
        friendly = (s.get("attributes") or {}).get("friendly_name") or eid
        choices[friendly.lower()] = eid

    if not choices:
        return {"action": "disambiguate", "candidates": []}

    if name_norm in choices:
        eid = choices[name_norm]
        return {"entity_id": eid, "friendly_name": name_norm, "confidence": 1.0}

    # fuzzy match but require alias-first; only allow a single high-confidence
    # fuzzy match; otherwise ask to disambiguate.
    best = difflib.get_close_matches(name_norm, list(choices.keys()), n=2, cutoff=0.8)
    if not best:
        # no close matches at high threshold -> disambiguate
        return {"action": "disambiguate", "candidates": []}
    if len(best) > 1:
        # ambiguous -> ask to disambiguate
        return {"action": "disambiguate", "candidates": best}
    b = best[0]
    # return conservative confidence
    return {"entity_id": choices[b], "friendly_name": b, "confidence": 0.85}

"""
Shared parsers responsibilities (design doc)

This module documents the responsibilities and guarantees expected of shared
parsing utilities used by skills. The actual parsing implementations are out
of scope for this doc; this file defines contracts and return types.

Responsibilities:

- Duration parsing
  - Input examples: "10 minutes", "in 2 hrs", "half an hour", "90s"
  - Output: integer number of seconds (int) or None if unparseable.
  - Guarantees: normalize ambiguous units to seconds; clamp >0; return None
    for invalid/overflowing inputs.

- Date/time parsing
  - Input examples: "tomorrow at 9am", "this afternoon", "2025-08-24 14:00"
  - Output: timezone-aware `datetime` (UTC) or None. When only a time is
    provided, use a sensible date (today/tomorrow) per skill context.
  - Guarantees: return `datetime` in UTC or None. Avoid guessing beyond the
    user's explicit intent; prefer returning None to a wrong assumption.

- Level parsing (brightness/volume)
  - Input examples: "set living room lights to 75%", "volume 20"
  - Output: integer in range 0..100 or None.
  - Guarantees: clamp to 0..100; accept both absolute numbers and
    percentage strings; return None for ambiguous text.

- Entity resolution
  - Behavior: resolve aliases via `alias_store`, then friendly-name cache,
    then fuzzy-match (difflib or similar) against HA `get_states()` results.
  - Output: canonical entity id string (e.g., "light.living_room") or None.
  - Guarantees: return entity id or None; prefer exact matches over fuzzy.

- Slot typing
  - Ensure returned slot values are canonical types (int, float, datetime,
    str, list, dict) or None. Do not return raw regex Match objects.

- Validation helpers
  - Provide validators to assert slot preconditions before execution (e.g.,
    require `when` for reminders or `entity_id` for device calls).

"""
