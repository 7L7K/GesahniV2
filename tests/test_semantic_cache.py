import os, asyncio
import pytest


def _clear_cache(vector_store):
    """Helper to remove all items from the QA cache."""
    vector_store.qa_cache.delete(ids=vector_store._qa_cache.get()["ids"])


def test_semantic_cache_hit(monkeypatch):
    os.environ["OLLAMA_URL"] = "http://x"
    os.environ["OLLAMA_MODEL"] = "llama3"
    os.environ["HOME_ASSISTANT_URL"] = "http://ha"
    os.environ["HOME_ASSISTANT_TOKEN"] = "token"
    from app import router
    from app.memory import vector_store

    # Clear cache
    _clear_cache(vector_store)

    # Seed cache with a prompt/answer pair
    original_prompt = "abcdefgh"  # length 8
    paraphrase = "ijklmnop"       # same length -> similarity 1.0
    vector_store.cache_answer("hash1", original_prompt, "cached")

    # Avoid side effects
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

    result = asyncio.run(router.route_prompt(paraphrase))
    assert result == "cached"


def test_record_feedback_preserves_metadata():
    from app.memory import vector_store

    # Start fresh
    _clear_cache(vector_store)

    prompt = "foo"
    answer = "bar"
    cache_id = "hash1"
    vector_store.cache_answer(cache_id, prompt, answer)

    meta_before = vector_store.qa_cache.get(ids=[cache_id])["metadatas"][0]

    vector_store.record_feedback(prompt, "up")

    meta_after = vector_store.qa_cache.get(ids=[cache_id])["metadatas"][0]

    assert meta_after["answer"] == answer
    assert meta_after["timestamp"] == meta_before["timestamp"]
    assert meta_after["feedback"] == "up"
