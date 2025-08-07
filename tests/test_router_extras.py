import asyncio
import os

import pytest
from fastapi import HTTPException


def _setup_env():
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"


def test_llama_override(monkeypatch):
    _setup_env()
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True

    async def fake_llama(prompt, model=None):
        for tok in ["ok"]:
            yield tok

    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "ALLOWED_LLAMA_MODELS", {"llama3"})
    result = asyncio.run(router.route_prompt("hello", "llama3", user_id="u"))
    assert result == "ok"


def test_cache_hit(monkeypatch):
    _setup_env()
    from app import router, llama_integration
    from app.memory import vector_store

    llama_integration.LLAMA_HEALTHY = False

    async def fake_gpt(prompt, model=None, system=None):
        return "cached", 0, 0, 0.0

    monkeypatch.setattr(router, "ask_gpt", fake_gpt)
    monkeypatch.setattr(router, "handle_command", lambda p: None)
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))
    monkeypatch.setattr(router, "pick_model", lambda p, i, t: ("gpt", "gpt-4"))
    monkeypatch.setattr(router.memgpt, "store_interaction", lambda *a, **k: None)
    monkeypatch.setattr(router, "add_user_memory", lambda *a, **k: None)

    try:
        vector_store.qa_cache.delete(ids=vector_store._qa_cache.get()["ids"])
        first = asyncio.run(router.route_prompt("hi", user_id="u"))
        assert first == "cached"

        async def explode(*args, **kwargs):
            raise RuntimeError("should not call")

        monkeypatch.setattr(router, "ask_gpt", explode)
        second = asyncio.run(router.route_prompt("hi", user_id="u"))
        assert second == "cached"
    finally:
        vector_store.close_store()


def test_low_conf_rejection(monkeypatch):
    _setup_env()
    from app import router, llama_integration

    llama_integration.LLAMA_HEALTHY = True

    async def low_conf(prompt, model=None):
        for tok in ["I don't know"]:
            yield tok

    monkeypatch.setattr(router, "ask_llama", low_conf)
    monkeypatch.setattr(router, "handle_command", lambda p: None)
    monkeypatch.setattr(router, "lookup_cached_answer", lambda p: None)
    monkeypatch.setattr(router, "pick_model", lambda p, i, t: ("llama", "llama3"))
    monkeypatch.setattr(router, "detect_intent", lambda p: ("chat", "high"))

    with pytest.raises(HTTPException):
        asyncio.run(router.route_prompt("hi", user_id="u"))


def test_ha_command(monkeypatch):
    _setup_env()
    from app import router, home_assistant

    async def fake_handle(prompt):
        return home_assistant.CommandResult(True, "done")

    monkeypatch.setattr(router, "handle_command", fake_handle)
    monkeypatch.setattr(router, "detect_intent", lambda p: ("other", "low"))
    monkeypatch.setattr(
        router, "ask_gpt", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad"))
    )

    result = asyncio.run(router.route_prompt("turn on", user_id="u"))
    assert result == "done"
