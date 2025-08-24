"""
Selector flow (design doc)

This module describes the selector that coordinates skill proposals and chooses
the best SkillResult according to the policy. It is a lightweight orchestration
layer and keeps backward compatibility with existing skills.

Selection flow summary:

1) Normalize input
   - Use `app/skills/base._normalize()` to get a canonical prompt for matching.

2) Propose step (per-skill)
   - For each skill instance in `app/skills.SKILLS`, try the following in order:
     a) If the skill implements `propose(prompt)`, call it. `propose` should
        return a `SkillResult`-shaped dict (see `contracts.py`) or a legacy
        output (string/bool).
     b) Otherwise, attempt a fast non-destructive check (e.g., `match()`)
        and, if matched, call a lightweight `preview()` or wrap a provisional
        `SkillResult` with a conservative confidence.

3) Normalize proposals
   - Wrap legacy outputs into the `SkillResult` shape. Default confidence for
     wrapped results is conservative (e.g., 0.5) unless the skill provided
     an explicit confidence.

4) Score & rank
   - Apply `app/skills/policy` scoring rules to adjust raw confidences. The
     policy may add bonuses for specificity, user preference, or recent
     successes.

5) Threshold & decide
   - If the top-ranked candidate's adjusted score >= STRONG_MATCH threshold,
     return it as the selected builtin skill result.
   - If in the WEAK_BAND, either ask for confirmation, defer to LLM, or
     proceed according to policy rules.
   - If no candidate clears thresholds, return `None` to indicate no match.

6) Telemetry
   - Return the chosen `SkillResult` plus the top-N candidates (top-3) and
     their scores for logging/inspection.

Compatibility notes:
- Existing skills that only return a string continue to work: selector will
  wrap their output into a `SkillResult` and score accordingly.

Performance note:
- `propose()` and any preview hooks on skills should be lightweight; avoid
  long blocking operations.

"""
from __future__ import annotations

import re
from typing import Any, List, Tuple

from .base import _normalize, SKILLS


async def select(prompt: str, top_n: int = 3) -> Tuple[dict | None, List[dict]]:
    """Lightweight selector compatible with existing skills.

    - Gathers matching skills by calling `match()` only (no side-effects).
    - Wraps matches into SkillResult-shaped dicts (legacy confidence=1.0).
    - Picks the top candidate deterministically (first match) to preserve
      current behavior. Returns chosen candidate and top-N candidates.
    """

    norm = _normalize(prompt)
    candidates: List[dict] = []
    matches: List[Tuple[Any, re.Match | None]] = []

    for skill in SKILLS:
        try:
            m = skill.match(norm)
        except Exception:
            m = None
        if not m:
            continue
        slots = (m.groupdict() or {}) if hasattr(m, "groupdict") else {}
        cand = {
            "handled": True,
            "text": None,
            "confidence": 1.0,
            "slots": slots,
            "why": getattr(skill, "skill_why", f"matched {skill.__class__.__name__}"),
            "idempotency_key": None,
            "events": None,
            "side_effects_required": False,
            "skill_name": skill.__class__.__name__,
        }
        candidates.append(cand)
        matches.append((skill, m))

    if not candidates:
        return None, []

    # Deterministic pick: first candidate (preserves existing behavior)
    chosen_idx = 0
    chosen_skill, chosen_match = matches[chosen_idx]
    chosen_cand = candidates[chosen_idx]

    # Execute the chosen skill to obtain the text response (may perform
    # side-effects as the skill implementations do today).
    try:
        if chosen_match is None:
            text = await chosen_skill.run(prompt, None)
        else:
            text = await chosen_skill.run(prompt, chosen_match)
    except Exception:
        text = None

    chosen_cand["text"] = text

    return chosen_cand, candidates[:top_n]

