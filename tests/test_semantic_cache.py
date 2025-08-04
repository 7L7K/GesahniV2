import os
import asyncio
import pytest


def _clear_cache(vector_store):
    """Helper to remove all items from the QA cache."""
    ids = vector_store.qa_cache.get(include=["ids"]).get("ids", [])
    if ids:
        vector_store.qa_cache.delete(ids=ids)


@pytest.fixture
def setup_cache(monkeypatch):
    # minimal env vars
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"

    from app import router
    from app.memory import vector_store

    # clear cache before each test
    _clear_cache(vector_store)

    # disable HA and builtin skills
    async def no_ha(prompt: str):
        return None

    monkeypatch.setattr(router, "handle_command", no_ha)
    monkeypatch.setattr(router, "CATALOG", [])

    # ensure neither Llama nor GPT are invoked
    async def fake_llama(prompt, model=None):
        raise AssertionError("llama should not be called")

    async def fake_gpt(prompt, model=None, system=None):
        raise AssertionError("gpt should not be called")

    monkeypatch.setattr(router, "ask_llama", fake_llama)
    monkeypatch.setattr(router, "ask_gpt", fake_gpt)

    # stub out history/analytics writes
    async def dummy(*args, **kwargs):
        return None

    monkeypatch.setattr(router, "append_history", dummy)
    monkeypatch.setattr(router, "record", dummy)

    return router, vector_store


def test_semantic_cache_hit_case_insensitive(setup_cache):
    router, vector_store = setup_cache
    vector_store.cache_answer("Hello World", "cached")
    result = asyncio.run(router.route_prompt("HELLO world", user_id="u"))
    assert result == "cached"


def test_semantic_cache_hit_whitespace_insensitive(setup_cache):
    router, vector_store = setup_cache
    vector_store.cache_answer("Hello World", "cached")
    result = asyncio.run(router.route_prompt("   hello world   ", user_id="u"))
    assert result == "cached"


def test_record_feedback_preserves_metadata():
    from app.memory import vector_store

    # Start with an empty cache
    _clear_cache(vector_store)

    prompt = "foo"
    answer = "bar"
    # we use the normalized hash as the cache key
    cache_id, _ = vector_store._normalize(prompt)
    vector_store.cache_answer(prompt, answer)

    meta_before = vector_store.qa_cache.get(ids=[cache_id], include=["metadatas"])["metadatas"][0]

    vector_store.record_feedback(prompt, "up")

    meta_after = vector_store.qa_cache.get(ids=[cache_id], include=["metadatas"])["metadatas"][0]

    assert meta_after["answer"] == answer
    assert meta_after["timestamp"] == meta_before["timestamp"]
    assert meta_after["feedback"] == "up"
