import os, sys, asyncio
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


def test_llama_error_sets_flag(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import llama_integration

    import httpx

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            pass

        async def post(self, *a, **k):
            raise httpx.TimeoutException("boom")

    monkeypatch.setattr(
        llama_integration,
        "httpx",
        type(
            "x",
            (),
            {
                "AsyncClient": lambda *a, **k: DummyClient(),
                "TimeoutException": httpx.TimeoutException,
                "HTTPError": httpx.HTTPError,
            },
        ),
    )
    llama_integration.LLAMA_HEALTHY = True
    res = asyncio.run(llama_integration.ask_llama("hi"))
    assert res["error"] == "timeout"
    assert llama_integration.LLAMA_HEALTHY is False


def test_router_skips_when_unhealthy(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router, llama_integration, analytics

    llama_integration.LLAMA_HEALTHY = False

    async def fake_llama(prompt, model=None):
        raise AssertionError("should not call llama")

    async def fake_gpt(prompt, model=None):
        return "ok", 0, 0, 0.0

    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    analytics._metrics = {"total": 0, "llama": 0, "gpt": 0, "fallback": 0}

    result = asyncio.run(router.route_prompt("hello"))
    assert result == "ok"
    assert analytics.get_metrics() == {"total": 1, "llama": 0, "gpt": 1, "fallback": 1}
