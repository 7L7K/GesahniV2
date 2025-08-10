import os
import asyncio


def test_planning_pass_carries_into_action(monkeypatch):
    os.environ["DETERMINISTIC_ROUTER"] = "1"
    from app import router as r

    # Force deterministic path without HA/cache
    monkeypatch.setattr(r, "handle_command", lambda p: None)
    monkeypatch.setattr(r, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(r, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(r, "LLAMA_HEALTHY", False)

    # Capture the built prompt to ensure plan is present in debug_info
    captured = {}

    def _build(user_prompt, **kwargs):
        captured["debug_info"] = kwargs.get("debug_info", "")
        return user_prompt, 10

    async def fake_ask(prompt, model=None, system=None, **kwargs):
        return "ok", 1, 1, 0.0

    monkeypatch.setattr(r.PromptBuilder, "build", staticmethod(_build))
    monkeypatch.setattr(r, "ask_gpt", fake_ask)

    out = asyncio.run(r.route_prompt("do x", user_id="u"))
    assert out == "ok"
    # Planning text should be carried in debug_info (contains 'PLAN:')
    assert "PLAN:" in captured.get("debug_info", "")


