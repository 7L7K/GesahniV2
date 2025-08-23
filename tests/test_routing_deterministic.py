import asyncio
import logging

from app.model_router import route_text


def test_flag_guard_legacy_router(monkeypatch):
    # Ensure we do not accidentally break legacy router without flag
    monkeypatch.delenv("DETERMINISTIC_ROUTER", raising=False)
    from app import router as r

    # monkeypatch pick_model to stable output to keep test deterministic
    monkeypatch.setattr(r, "pick_model", lambda *a, **k: ("gpt", "gpt-4o"))

    async def fake_gpt(prompt, model=None, system=None, **kwargs):
        return "ok", 0, 0, 0.0

    monkeypatch.setattr(r, "ask_gpt", fake_gpt)
    monkeypatch.setattr(r, "handle_command", lambda p: None)
    monkeypatch.setattr(r, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(r.PromptBuilder, "build", staticmethod(lambda *a, **k: (a[0], 1)))

    assert asyncio.run(r.route_prompt("ask gpt please", user_id="u")) == "ok"


def test_deterministic_router_path(caplog):
    # Call route_text directly to verify logging of decision reason
    with caplog.at_level(logging.DEBUG, logger="app.model_router"):
        decision = route_text(user_prompt="hello" * 100, prompt_tokens=300)
    assert decision.model == "gpt-4.1-nano"
    assert "long-prompt" in caplog.text


