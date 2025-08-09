import os
import asyncio

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

    import asyncio
    assert asyncio.run(r.route_prompt("ask gpt please", user_id="u")) == "ok"


def test_deterministic_router_path(monkeypatch):
    os.environ["DETERMINISTIC_ROUTER"] = "1"
    from app import router as r

    async def fake_ask(prompt, model=None, system=None, **kwargs):
        # Always fail self-check at nano to trigger escalation to 4.1-nano
        return "not sure", 10, 1, 0.0

    monkeypatch.setattr(r, "ask_gpt", fake_ask)
    monkeypatch.setattr(r, "handle_command", lambda p: None)
    monkeypatch.setattr(r, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(r.PromptBuilder, "build", staticmethod(lambda *a, **k: (a[0], 300)))

    import asyncio
    out = asyncio.run(r.route_prompt("please answer", user_id="u"))
    assert isinstance(out, str)


