import os
import asyncio

import pytest
from fastapi import HTTPException


def _setup_env():
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"


def test_llama_circuit_open_routes_to_gpt(monkeypatch):
    _setup_env()
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True
    router.llama_circuit_open = True

    async def fake_gpt(**kwargs):
        return "gpt-ok"

    async def fail_llama(**kwargs):  # pragma: no cover - should not be called
        raise RuntimeError("llama should not run")

    called = {"pick": False}

    def fake_pick(prompt, intent, tokens):
        called["pick"] = True
        return "gpt", "gpt-4"

    monkeypatch.setattr(router, "_call_gpt", fake_gpt)
    monkeypatch.setattr(router, "_call_llama", fail_llama)
    monkeypatch.setattr(router, "handle_command", lambda p: None)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(router, "pick_model", fake_pick)
    monkeypatch.setattr(router.PromptBuilder, "build", lambda *a, **k: (a[0], 0))

    result = asyncio.run(router.route_prompt("hi", user_id="u"))
    assert result == "gpt-ok"
    assert called["pick"]
    assert not llama_integration.LLAMA_HEALTHY


def test_gpt_failure_falls_back_to_llama(monkeypatch):
    _setup_env()
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True
    router.LLAMA_HEALTHY = True

    async def fail_gpt(**kwargs):
        raise RuntimeError("boom")

    async def fake_llama(**kwargs):
        return "llama-ok"

    monkeypatch.setattr(router, "_call_gpt", fail_gpt)
    monkeypatch.setattr(router, "_call_llama", fake_llama)
    monkeypatch.setattr(router, "handle_command", lambda p: None)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(router, "pick_model", lambda p, i, t: ("gpt", "gpt-4"))
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))

    result = asyncio.run(router.route_prompt("hi", user_id="u"))
    assert result == "llama-ok"


def test_gpt_failure_raises_when_llama_unhealthy(monkeypatch):
    _setup_env()
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = False
    router.LLAMA_HEALTHY = False

    async def fail_gpt(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(router, "_call_gpt", fail_gpt)
    monkeypatch.setattr(router, "handle_command", lambda p: None)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(router, "pick_model", lambda p, i, t: ("gpt", "gpt-4"))
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))

    with pytest.raises(HTTPException):
        asyncio.run(router.route_prompt("hi", user_id="u"))


def test_gpt_override_failure_falls_back_to_llama(monkeypatch):
    _setup_env()
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True
    router.LLAMA_HEALTHY = True

    async def fail_override(*args, **kwargs):
        raise RuntimeError("boom")

    async def fake_llama(**kwargs):
        return "llama-ok"

    monkeypatch.setattr(router, "_call_gpt_override", fail_override)
    monkeypatch.setattr(router, "_call_llama", fake_llama)
    monkeypatch.setattr(router, "ALLOWED_GPT_MODELS", {"gpt-4"})

    result = asyncio.run(router.route_prompt("hi", "gpt-4", user_id="u"))
    assert result == "llama-ok"


def test_empty_llama_response_falls_back_to_gpt(monkeypatch):
    _setup_env()
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True
    router.LLAMA_HEALTHY = True

    def fake_llama(**kwargs):
        return ""

    async def fake_gpt(**kwargs):
        return "gpt-ok"

    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "_call_gpt", fake_gpt)
    monkeypatch.setattr(router, "handle_command", lambda p: None)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(router, "pick_model", lambda p, i, t: ("llama", "llama3"))
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))

    result = asyncio.run(router.route_prompt("hi", user_id="u"))
    assert result == "gpt-ok"
    assert llama_integration.LLAMA_HEALTHY is False


def test_low_conf_llama_response_falls_back_to_gpt(monkeypatch):
    _setup_env()
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True
    router.LLAMA_HEALTHY = True

    def fake_llama(**kwargs):
        return "I don't know"

    async def fake_gpt(**kwargs):
        return "gpt-ok"

    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "_call_gpt", fake_gpt)
    monkeypatch.setattr(router, "handle_command", lambda p: None)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(router, "pick_model", lambda p, i, t: ("llama", "llama3"))
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))

    result = asyncio.run(router.route_prompt("hi", user_id="u"))
    assert result == "gpt-ok"
    assert llama_integration.LLAMA_HEALTHY is False
