def detect_intent(prompt: str) -> tuple[str, str]:
    prompt_l = prompt.lower()
    if any(kw in prompt_l for kw in ("turn on", "turn off")):
        return "control", "high"
    if len(prompt_l.split()) < 10:
        return "chat", "medium"
    return "unknown", "low"
