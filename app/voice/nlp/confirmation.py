"""Confirmation heuristics scaffold."""


def needs_confirmation(intent_action: str) -> bool:
    return intent_action in {"play", "add", "assist"}


def build_prompt(intent_action: str) -> str:
    return {
        "play": "Do you want me to play music now?",
        "add": "Should I save that reminder?",
        "assist": "Do you need me to call a caregiver?",
    }.get(intent_action, "Is this correct?")


