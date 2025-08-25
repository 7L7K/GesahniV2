from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class Candidate:
    skill: Any
    pattern: Any
    score: float
    reasons: Dict[str, str]

"""
SkillResult shape (fields only) — design document

This module documents the canonical SkillResult contract used by the skill
selection/selector layer. This file intentionally contains only documentation
(descriptive fields and semantics) and no executable code.

SkillResult fields (names, intended types, and short description):

- handled: bool
  - True when the skill indicates it can (or did) handle the prompt. False
    indicates the skill declines.

- text: str | None
  - The spoken/text response the skill would return to the user. May be None
    for skills that only emit events and return no user-facing text.

- confidence: float
  - A float in the range [0.0, 1.0] representing the skill's internal
    confidence that the result is appropriate for the input. Interpretation
    is governed by the system policy (see `policy.py`). If a skill cannot
    compute a confidence, the selector will wrap the skill's result with a
    conservative default (see selector behavior).

- slots: dict[str, Any]
  - Named extraction results (e.g., {"when": <datetime>, "amount": 10}).
    Slot values should be canonical types where possible (datetime, int,
    float, str). Missing or unparseable slots should be omitted or set to
    None.

- why: str | None
  - Short, human-readable explanation for observability (one-line). e.g.
    "matched brightness pattern, parsed level=75". Must not include
    sensitive data (PII). This is used for telemetry/logging only.

- idempotency_key: str | None
  - Optional opaque key that can be used to detect duplicate side-effect
    execution requests. Skills producing side effects should return a stable
    idempotency key derived from the intent + canonical slots when possible.

- events: list[dict] | None
  - Optional structured events the skill would emit for downstream systems
    (e.g., {"type": "ha_call", "service": "light.turn_on", "args": {...}}).

- side_effects_required: bool
  - Indicates whether executing this result will perform external state
    changes (DB writes, HA calls). If True the router or an executor will be
    responsible for invoking the action (see policy for validation rules).

Notes on usage and contract guarantees:

- Backwards compatibility: Existing skills may still return a simple string
  or raise an exception. The selector wraps legacy outputs into a
  SkillResult with `handled=True`, `text=<string>`, `confidence=<default>`.

- Confidence semantics: See `policy.py` for threshold definitions and how
  confidence affects selection. All confidences are treated as probabilities
  (higher == more confident).

- Slots/Types: Parsers should normalize units (seconds for durations,
  0–100 integers for levels, ISO 8601 for datetimes where feasible).

- WHY hygiene: `why` exists for logs; it must be short, non-sensitive, and
  suitable for admin debugging only.

"""
