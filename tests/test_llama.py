import os, sys
import pytest
os.environ.setdefault("OLLAMA_URL", "http://test")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.llama_integration import llama_status, ask_llama
import httpx

class MockClient:
    def __init__(self, *a, **k):
        pass
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        pass
    async def get(self, url):
        class R:
            def raise_for_status(self):
                pass
            def json(self):
                return {"models":[{"name":"llama3"}]}
        return R()
    async def post(self, url, json, timeout):
        class R:
            def raise_for_status(self):
                pass
            def json(self):
                return {"response":"hi"}
        return R()

@pytest.mark.asyncio
async def test_llama_status_returns_healthy(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: MockClient())
    result = await llama_status()
    assert result["status"] == "healthy"
    assert isinstance(result["latency_ms"], int)
