import os
import sys
import asyncio
import logging
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class DummyOpenAIEmbeddings:
    def __init__(self):
        self.last_model = None

    def create(self, model: str, input: str):  # pragma: no cover - simple stub
        self.last_model = model

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


def test_embed_model_env(monkeypatch):
    os.environ["EMBEDDING_BACKEND"] = "openai"
    from app import embeddings

    dummy = DummyOpenAIClient()
    monkeypatch.setattr(embeddings, "get_openai_client", lambda: dummy)
    embeddings._embed_openai_sync.cache_clear()

    monkeypatch.setenv("EMBED_MODEL", "m1")
    embeddings._embed_openai_sync("hello", 0)
    assert dummy.embeddings.last_model == "m1"

    embeddings._embed_openai_sync.cache_clear()
    monkeypatch.setenv("EMBED_MODEL", "m2")
    embeddings._embed_openai_sync("hello", 1)
    assert dummy.embeddings.last_model == "m2"


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


@pytest.mark.parametrize("backend", ["openai", "llama", "stub"])
def test_embedding_backend_logged(monkeypatch, caplog, backend):
    from app import embeddings

    caplog.set_level(logging.DEBUG)
    if backend == "openai":
        monkeypatch.setenv("EMBEDDING_BACKEND", "openai")
        monkeypatch.setattr(embeddings, "get_openai_client", lambda: DummyOpenAIClient())
        asyncio.run(embeddings.embed("hi"))
    elif backend == "llama":
        monkeypatch.setenv("EMBEDDING_BACKEND", "llama")
        monkeypatch.setenv("LLAMA_EMBEDDINGS_MODEL", "/tmp/model.gguf")
        monkeypatch.setattr(embeddings, "Llama", lambda *a, **k: DummyLlama())
        embeddings._llama_model = None
        asyncio.run(embeddings.embed("hi"))
    else:
        monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
        embeddings.embed_sync("hi")

    assert f"Embedding backend: {backend}" in caplog.text
