import pytest


def test_embed_sync_stub_for_memory_store(monkeypatch):
    from app import embeddings as emb

    monkeypatch.setenv("VECTOR_STORE", "memory")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")

    v = emb.embed_sync("hello")
    assert isinstance(v, list) and len(v) == 8


@pytest.mark.asyncio
async def test_benchmark_stub(monkeypatch):
    from app import embeddings as emb

    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    stats = await emb.benchmark("hello", iterations=2)
    assert set(["latency", "throughput"]).issubset(stats.keys())


