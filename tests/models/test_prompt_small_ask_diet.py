from __future__ import annotations

from app.prompt_builder import PromptBuilder


def test_small_ask_prompt_is_thin(monkeypatch):
    monkeypatch.setenv("PROMETHEUS_ENABLED", "0")
    text, toks = PromptBuilder.build(
        "what's my favorite color",
        session_id="s1",
        user_id="u1",
        small_ask=True,
        profile_facts={"favorite_color": "blue"},
    )
    assert "[USER_PROFILE_FACTS]" in text
    # Minimal size – well under 200 tokens
    assert toks < 200
