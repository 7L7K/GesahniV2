import os, sys
import pytest
os.environ.setdefault("OLLAMA_URL", "http://test")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
os.environ.setdefault("HOME_ASSISTANT_URL", "http://test")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import analytics
from app.router import route_prompt

@pytest.mark.asyncio
async def test_router_fallback_metrics_updated(monkeypatch):
    async def mock_handle(prompt):
        return None
    async def mock_llama(prompt):
        return {"error":"timeout","llm_used":"llama3"}
    async def mock_gpt(prompt):
        return "gpt"
    monkeypatch.setattr("app.router.handle_command", mock_handle)
    monkeypatch.setattr("app.router.ask_llama", mock_llama)
    monkeypatch.setattr("app.router.ask_gpt", mock_gpt)
    monkeypatch.setattr("app.router.detect_intent", lambda p: ("chat","high"))
    metrics = analytics.get_metrics()
    await route_prompt("hello")
    assert metrics["gpt"] >= 1
    assert metrics["fallback"] >= 1
