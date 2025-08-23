import pytest


@pytest.mark.asyncio
async def test_embed_async_stub_when_pytest_flag(monkeypatch):
    from app import embeddings as emb

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")
    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")

    v = await emb.embed("hello")
    assert isinstance(v, list) and len(v) == 8
