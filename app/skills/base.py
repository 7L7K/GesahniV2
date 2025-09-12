from __future__ import annotations

import re
import unicodedata  # ← NEW
from abc import ABC, abstractmethod
from re import Pattern

from ..history import append_history
from ..telemetry import log_record_var


class Skill(ABC):
    """Abstract base class for all built in skills."""

    PATTERNS: list[Pattern[str]] = []

    # Optional short human-readable "why" string a skill can set when it runs.
    # This should be a brief explanation (string) for observability only and
    # must not contain sensitive data. It is written to the current
    # telemetry LogRecord via `log_record_var` when available.
    skill_why: str | None = None

    def match(self, prompt: str) -> re.Match | None:
        for pat in self.PATTERNS:
            m = pat.search(prompt)
            if m:
                return m
        return None

    @abstractmethod
    async def run(self, prompt: str, match: re.Match) -> str:
        """Execute the skill and return the response text."""
        raise NotImplementedError

    async def handle(self, prompt: str) -> str:
        """Convenience wrapper used by the router."""
        m = self.match(prompt)
        if not m:
            raise ValueError("no pattern matched")
        # run() returns a text response. Skills may set `self.skill_why` as a
        # short explanation which the router will log; don't alter return type.
        resp = await self.run(prompt, m)
        return resp


SKILLS: list[Skill] = []


# ---------- NEW helper ----------
def _normalize(text: str) -> str:
    """Replace curly quotes / fancy dashes and collapse whitespace.

    This makes regexes far more resilient to pasted Unicode and odd spacing.
    """
    text = unicodedata.normalize("NFKD", text)
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "—": "-",
        "–": "-",
        "…": "...",
        "\u00A0": " ",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    # Collapse multiple spaces/tabs/newlines into single spaces
    text = " ".join(text.split())
    return text


# ---------------------------------


async def check_builtin_skills(prompt: str) -> str | None:
    """Return a response from the first matching skill or ``None``.

    Any matched skill response is also logged to the history file using the
    skill class name as ``engine_used``.
    """
    # Scoring-based selector (best-match)
    from .contracts import Candidate

    norm = _normalize(prompt)  # use normalized text for matching
    candidates: list[Candidate] = []
    for skill in SKILLS:
        m = skill.match(norm)
        if not m:
            continue
        # pattern_score = proportion of named groups that were matched
        groups = m.groupdict()
        total_named = len([p for p in m.re.pattern.split("(?P") if p]) if m.re.pattern else 0
        matched_named = len([k for k, v in groups.items() if v])
        pattern_score = (matched_named / max(1, len(groups))) if groups else 0.5
        # context bonus: alias hits or recent usage (simple heuristic)
        context_bonus = 0.0
        try:
            # alias check: if skill name appears in prompt give small bonus
            if skill.__class__.__name__.lower().replace("skill", "") in norm:
                context_bonus += 0.05
        except Exception:
            pass
        score = min(1.0, pattern_score + context_bonus)
        reasons = {"pattern_score": f"{pattern_score:.2f}", "context_bonus": f"{context_bonus:.2f}"}
        candidates.append(Candidate(skill=skill, pattern=m, score=score, reasons=reasons))

    # Sort descending
    candidates.sort(key=lambda c: c.score, reverse=True)

    # Logging top-3
    top3 = candidates[:3]
    rec = log_record_var.get()
    if rec is not None:
        rec.candidates = [(c.skill.__class__.__name__, c.score, c.reasons) for c in top3]

    if not candidates:
        return None

    top = candidates[0]
    # Decision thresholds
    if top.score >= 0.8:
        resp = await top.skill.run(prompt, top.pattern)
        if rec is not None:
            rec.matched_skill = top.skill.__class__.__name__
            rec.match_confidence = top.score
            rec.engine_used = top.skill.__class__.__name__
            rec.response = str(resp)
            # standardized telemetry fields
            rec.normalized_prompt = norm
            rec.chosen_skill = top.skill.__class__.__name__
            rec.confidence = top.score
            rec.slots = top.pattern.groupdict() if top.pattern else None
            rec.why = getattr(top.skill, "skill_why", None)
            rec.idempotency_key = None
            rec.deduped = False
            rec.skipped_llm = False
        await append_history(prompt, top.skill.__class__.__name__, str(resp))
        return resp

    if 0.5 <= top.score < 0.8:
        # consider top-3; if top two are close, escalate (fallback to LLM)
        if len(candidates) >= 2 and (top.score - candidates[1].score) < 0.1:
            return None
        resp = await top.skill.run(prompt, top.pattern)
        if rec is not None:
            rec.matched_skill = top.skill.__class__.__name__
            rec.match_confidence = top.score
            rec.engine_used = top.skill.__class__.__name__
            rec.response = str(resp)
            # standardized telemetry fields for partial confidence
            rec.normalized_prompt = norm
            rec.chosen_skill = top.skill.__class__.__name__
            rec.confidence = top.score
            rec.slots = top.pattern.groupdict() if top.pattern else None
            rec.why = getattr(top.skill, "skill_why", None)
            rec.idempotency_key = None
            rec.deduped = False
            rec.skipped_llm = False
        await append_history(prompt, top.skill.__class__.__name__, str(resp))
        return resp

    # below 0.5 -> no builtin; route to LLM
    return None
