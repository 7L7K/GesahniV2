import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest

import asyncio
from fastapi import HTTPException

def test_router_fallback_metrics_updated(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router, analytics, llama_integration
    llama_integration.LLAMA_HEALTHY = True
    async def fake_llama(prompt, model=None):
        return {"error": "timeout", "llm_used": "llama3"}

    async def fake_gpt(prompt, model=None):
        return "ok", 0, 0, 0.0

    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    analytics._metrics = {
        "total": 0,
        "llama": 0,
        "gpt": 0,
        "fallback": 0,
        "session_count": 0,
        "transcribe_ms": 0,
        "transcribe_count": 0,
        "transcribe_errors": 0,
    }

    result = asyncio.run(router.route_prompt("hello"))
    assert result == "ok"
    m = analytics.get_metrics()
    assert m["total"] == 1
    assert m["gpt"] == 1
    assert m["fallback"] == 1


def test_gpt_override(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True

    async def fake_gpt(prompt, model=None):
        return model, 0, 0, 0.0

    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    monkeypatch.setattr(router, "ALLOWED_GPT_MODELS", {"gpt-4"})
    result = asyncio.run(router.route_prompt("hi", "gpt-4"))
    assert result == "gpt-4"


def test_gpt_override_invalid(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router

    monkeypatch.setattr(router, "ALLOWED_GPT_MODELS", {"gpt-4"})
    with pytest.raises(HTTPException):
        asyncio.run(router.route_prompt("hi", "gpt-3"))


def test_complexity_checks(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True

    async def fake_gpt(prompt, model=None):
        return "gpt", 0, 0, 0.0

    async def fake_llama(prompt, model=None):
        return "llama"

    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    monkeypatch.setattr(router, "ask_llama", fake_llama)

    long_prompt = "word " * 31
    assert asyncio.run(router.route_prompt(long_prompt)) == "gpt"

    kw_prompt = "please analyze this"
    assert asyncio.run(router.route_prompt(kw_prompt)) == "gpt"


def test_skill_metrics(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router, analytics

    class DummySkill:
        name = "dummy"

        async def handle(self, prompt):
            return "done"

    monkeypatch.setattr(router, "CATALOG", [(["dummy"], DummySkill)])
    analytics._metrics = {
        "total": 0,
        "llama": 0,
        "gpt": 0,
        "fallback": 0,
        "session_count": 0,
        "transcribe_ms": 0,
        "transcribe_count": 0,
        "transcribe_errors": 0,
    }
    result = asyncio.run(router.route_prompt("dummy task"))
    assert result == "done"
    m = analytics.get_metrics()
    assert m["total"] == 1
    assert m["gpt"] == 0
    assert m["llama"] == 0
