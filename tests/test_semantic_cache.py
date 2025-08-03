import os
import asyncio
import pytest


@pytest.fixture
def setup_cache(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router
    from app.memory import vector_store

    vector_store.qa_cache.delete(ids=vector_store._qa_cache.get()["ids"])

    async def no_ha(prompt: str):
        return None
    monkeypatch.setattr(router, "handle_command", no_ha)
    monkeypatch.setattr(router, "CATALOG", [])

    async def fake_llama(prompt, model=None):
        raise AssertionError("llama should not be called")

    async def fake_gpt(prompt, model=None, system=None):
        raise AssertionError("gpt should not be called")

    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "ask_gpt", fake_gpt)

    async def dummy(*args, **kwargs):
        return None

    monkeypatch.setattr(router, "append_history", dummy)
    monkeypatch.setattr(router, "record", dummy)
    return router, vector_store


def test_semantic_cache_hit_case_insensitive(setup_cache):
    router, vector_store = setup_cache
    vector_store.cache_answer("Hello World", "cached")
    result = asyncio.run(router.route_prompt("HELLO world"))
    assert result == "cached"


def test_semantic_cache_hit_whitespace_insensitive(setup_cache):
    router, vector_store = setup_cache
    vector_store.cache_answer("Hello World", "cached")
    result = asyncio.run(router.route_prompt("   hello world   "))
    assert result == "cached"
