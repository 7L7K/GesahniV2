import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import pytest

import asyncio

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
    analytics._metrics = {"total": 0, "llama": 0, "gpt": 0, "fallback": 0}

    result = asyncio.run(router.route_prompt("hello"))
    assert result == "ok"
    assert analytics.get_metrics() == {"total": 1, "llama": 0, "gpt": 1, "fallback": 1}
