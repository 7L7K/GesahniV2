import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio


class DummyResponse:
    status_code = 200
    text = "{}"

    def raise_for_status(self):
        pass

    def json(self):
        return {"response": "pong"}


class DummyClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def request(self, method, url, **kwargs):
        return DummyResponse()


def test_llama_status_returns_healthy(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    from app import llama_integration

    monkeypatch.setattr(
        llama_integration,
        "httpx",
        type("x", (), {"AsyncClient": lambda *a, **k: DummyClient()}),
    )
    res = asyncio.run(llama_integration.get_status())
    assert res["status"] == "healthy"
    assert "latency_ms" in res
