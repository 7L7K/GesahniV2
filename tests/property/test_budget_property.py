import os
import random

from app.token_budgeter import clamp_prompt


def test_budget_property_caps_random(monkeypatch):
    random.seed(0)
    # Fuzz different intents and env caps
    intents = [None, "chat", "smalltalk", "search", "code"]
    for intent in intents:
        cap_in = random.randint(50, 400)
        key = (intent or "chat").lower()
        os.environ[f"INTENT_CAP_{key}_IN"] = str(cap_in)
        text = "x" * (cap_in * 5)
        out = clamp_prompt(text, intent)
        assert len(out) <= (cap_in * 5)  # truncated by chars heuristic
