from typing import Tuple

KEYWORDS = {"turn", "switch", "lights", "light"}

CONFIDENCE_LEVELS = ["low", "medium", "high"]

def detect_intent(prompt: str) -> Tuple[str, str]:
    lower = prompt.lower()
    if any(k in lower for k in KEYWORDS):
        return "command", "high"
    return "chat", "medium"
