import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio


class DummyOpenAIEmbeddings:
    def create(self, model: str, input: str):  # pragma: no cover - simple stub
        class Resp:
            data = [type("d", (), {"embedding": [1.0, 2.0, 3.0]})()]

        return Resp()


class DummyOpenAIClient:
    embeddings = DummyOpenAIEmbeddings()


class DummyLlama:
    def create_embedding(self, text: str):  # pragma: no cover - simple stub
        return {"data": [{"embedding": [4.0, 5.0, 6.0]}]}


def test_embed_openai(monkeypatch):
    os.environ["EMBEDDING_BACKEND"] = "openai"
    from app import embeddings

    monkeypatch.setattr(embeddings, "get_openai_client", lambda: DummyOpenAIClient())

    res = asyncio.run(embeddings.embed("hi"))
    assert res == [1.0, 2.0, 3.0]


def test_embed_llama(monkeypatch):
    os.environ["EMBEDDING_BACKEND"] = "llama"
    os.environ["LLAMA_EMBEDDINGS_MODEL"] = "/tmp/model.gguf"
    from app import embeddings

    monkeypatch.setattr(embeddings, "Llama", lambda *a, **k: DummyLlama())
    embeddings._llama_model = None

    res = asyncio.run(embeddings.embed("hi"))
    assert res == [4.0, 5.0, 6.0]


def test_benchmark(monkeypatch):
    from app import embeddings

    async def fake_embed(text: str):
        return [0.0]

    monkeypatch.setattr(embeddings, "embed", fake_embed)

    metrics = asyncio.run(embeddings.benchmark("x", iterations=5))
    assert "latency" in metrics and "throughput" in metrics
