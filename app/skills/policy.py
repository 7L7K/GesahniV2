"""
Policy definitions and scoring rules (design doc)

This module documents numeric thresholds and routing rules used by the
skills selector to interpret confidence and decide whether to select a
builtin skill or escalate to the LLM.

Numeric thresholds (human terms):

- STRONG_MATCH = 0.80
  - Any candidate with adjusted score >= 0.80 is considered a strong match
    and will be selected immediately (no LLM fallback required).

- WEAK_BAND = [0.50, 0.80)
  - Candidates with scores in this band are plausible but uncertain. Policy
    options include asking for confirmation, deferring to the LLM, or using
    ancillary signals (user preference, recency) to decide.

- NO_MATCH = < 0.50
  - Below 0.50 the selector treats candidates as non-matching and routes
    to the LLM.

Scoring adjustments / tie-breakers (human-readable):

- Specificity bonus
  - If a skill's matched pattern contains named capturing groups that are
    non-empty (e.g., a captured "name" or "amount"), award a small bonus
    (e.g., +0.05) to reflect higher intent specificity.

- User-preference bonus
  - If the user has a stored preference favoring a particular skill (via
    memory/profile), award up to +0.05.

- Recent-success bonus
  - If the same skill succeeded for the same user recently, grant a small
    boost (e.g., +0.03) to prefer consistent behavior.

- Specific vs generic tie-breaker
  - If two candidates tie numerically, prefer the one with more filled
    slots (more named groups parsed). If still tied, prefer the skill that
    appears earlier in the deterministic `SKILL_CLASSES` ordering.

Escalation rules:

- If top candidate in WEAK_BAND and user is an interactive client, prefer
  asking for a 1-bit confirmation ("Do you want me to set a timer for 10
  minutes?"). For non-interactive clients, prefer LLM fallback.

- If multiple candidates are close (within 0.02), include top-3 in router
  telemetry so humans can inspect and tune patterns.

Safety & side-effects:

- Actions that require side effects (writes, HA calls) must clear the
  STRONG_MATCH threshold or be accompanied by explicit user confirmation
  unless a validated idempotency_key is present.

- The executor must re-validate slots before executing side effects; the
  selector does not itself perform side-effects.

"""

# Numeric thresholds (machine-usable)
# Keep these constants here so selector and router can import them.
STRONG_MATCH: float = 0.80
WEAK_BAND_LO: float = 0.50
WEAK_BAND_HI: float = STRONG_MATCH

# Scoring bonuses
SPECIFICITY_BONUS: float = 0.05
USER_PREFERENCE_BONUS: float = 0.05
RECENT_SUCCESS_BONUS: float = 0.03
