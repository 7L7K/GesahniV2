"""Simple heuristic intent detector."""

from .skills.smalltalk_skill import is_greeting


def detect_intent(prompt: str) -> tuple[str, str]:
    """Classify a user prompt into broad intent buckets.

    The checks run in the following order:

    1. **Greeting** – phrases like "hi" or "yo" short‑circuit to
       ``("smalltalk", "low")``.
    2. **Control** – commands containing "turn on"/"turn off" are treated as
       high‑confidence automation requests and return
       ``("control", "high")``.
    3. **Chat** – prompts under ten words are considered casual chat and yield
       ``("chat", "medium")``.
    4. **Unknown** – anything else is labeled ``("unknown", "low")``.

    The function intentionally favors control phrases with high confidence so
    they are executed before more ambiguous chat heuristics.
    """

    prompt_lower = prompt.lower()
    if is_greeting(prompt):
        return "smalltalk", "low"
    if any(kw in prompt_lower for kw in ("turn on", "turn off")):
        return "control", "high"
    parts = prompt_lower.split()
    if len(parts) < 10:
        if len(parts) == 1:
            return "unknown", "low"
        return "chat", "medium"
    return "unknown", "low"
