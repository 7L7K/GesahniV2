import os
import sys
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_llama_error_sets_flag(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import llama_integration

    async def fake_json_request(*args, **kwargs):
        return None, "network_error"

    monkeypatch.setattr(llama_integration, "json_request", fake_json_request)
    llama_integration.LLAMA_HEALTHY = True
    res = asyncio.run(llama_integration.ask_llama("hi"))
    assert res["error"] == "timeout"
    assert llama_integration.LLAMA_HEALTHY is False


def test_llama_model_guard(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    from app import llama_integration

    llama_integration.OLLAMA_MODEL = None
    res = asyncio.run(llama_integration.ask_llama("hi"))
    assert res == {"error": "model_not_set"}


def test_router_skips_when_unhealthy(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router, llama_integration, analytics

    llama_integration.LLAMA_HEALTHY = False

    async def fake_llama(prompt, model=None):
        raise AssertionError("should not call llama")

    async def fake_gpt(prompt, model=None, system=None, **kwargs):
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

    result = asyncio.run(router.route_prompt("hello", user_id="u"))
    assert result == "ok"
    m = analytics.get_metrics()
    assert m["total"] == 1
    assert m["gpt"] == 1
    assert m["fallback"] == 1
