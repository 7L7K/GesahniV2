from __future__ import annotations

import time
from typing import List, Dict, Tuple

from . import SKILLS
from ..metrics import SKILL_HITS_TOTAL, SELECTOR_LATENCY_MS, SKILL_CONF_BUCKET


def score_skill(skill, match) -> Tuple[float, Dict[str, float]]:
    groups = match.groupdict() if match else {}
    matched = len([v for v in groups.values() if v])
    total = max(1, len(groups))
    pattern_score = matched / total
    context_bonus = 0.0
    # boost when both a verb/amount and a unit are present (stronger signal)
    try:
        if match is not None:
            g = match.groupdict()
            if g.get("amount") and g.get("unit"):
                pattern_score = min(1.0, pattern_score + 0.05)
    except Exception:
        pass
    # Context bonus: check if skill's canonical name or known aliases appear in the prompt
    try:
        skill_base = skill.__class__.__name__.lower()
        canon = skill_base.replace("skill", "")
        aliases = {canon}
        # Small explicit alias map for common abbreviated names
        _ALIAS_MAP = {"timerskill": {"timer"}}
        aliases = aliases.union(_ALIAS_MAP.get(skill_base, set()))
        prompt_text = (match.string or "").lower()
        for a in aliases:
            if a and a in prompt_text:
                context_bonus += 0.05
                break
    except Exception:
        pass
    # recent success bonus stub
    recent_success = 0.0
    score = min(1.0, pattern_score + context_bonus + recent_success)
    return score, {"pattern_score": pattern_score, "context_bonus": context_bonus}


async def select(prompt: str, top_n: int = 3) -> Tuple[Dict | None, List[Dict]]:
    start = time.monotonic()
    candidates = []
    for s in SKILLS:
        m = s.match(prompt)
        if not m:
            continue
        sc, reasons = score_skill(s, m)
        candidates.append({"skill": s, "score": sc, "match": m, "reasons": reasons})

    candidates.sort(key=lambda x: x["score"], reverse=True)
    top = candidates[:top_n]
    # telemetry
    SELECTOR_LATENCY_MS.observe((time.monotonic() - start) * 1000)
    for c in top:
        SKILL_CONF_BUCKET.observe(c["score"])
    if not candidates:
        return None, []
    chosen = candidates[0]
    SKILL_HITS_TOTAL.labels(skill=chosen["skill"].__class__.__name__).inc()
    return {"skill_name": chosen["skill"].__class__.__name__, "text": await chosen["skill"].run(prompt, chosen["match"].group(0) if chosen["match"] else None), "why": chosen["reasons"]}, [
        {"skill_name": c["skill"].__class__.__name__, "score": c["score"], "reasons": c["reasons"]} for c in top
    ]

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

    # Safety-net: if no candidates but the prompt contains a timer heuristic,
    # inject a TimerSkill candidate at 0.8 confidence so timers aren't missed.
    if not candidates:
        norm_text = norm if isinstance(norm, str) else (norm[1] if isinstance(norm, tuple) else str(prompt))
        if isinstance(norm_text, tuple):
            norm_text = norm_text[1]
        norm_text = (norm_text or "").lower()
        if "timer" in norm_text or "set a timer" in norm_text:
            # try to find amount/unit via regex to build a minimal match
            amount_re = re.search(r"(?P<amount>\d+)\s*(?P<unit>seconds?|second|minutes?|minute|mins?|hrs?|hours?)", norm_text)
            timer_skill = None
            for s in SKILLS:
                if s.__class__.__name__ == "TimerSkill":
                    timer_skill = s
                    break
            if timer_skill is not None:
                if amount_re:
                    chosen_match = amount_re
                else:
                    chosen_match = None
                cand = {
                    "handled": True,
                    "text": None,
                    "confidence": 0.8,
                    "slots": (chosen_match.groupdict() if chosen_match is not None else {}),
                    "why": "injected_timer_heuristic",
                    "idempotency_key": None,
                    "events": None,
                    "side_effects_required": False,
                    "skill_name": timer_skill.__class__.__name__,
                }
                candidates.append(cand)
                matches.append((timer_skill, chosen_match))

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

