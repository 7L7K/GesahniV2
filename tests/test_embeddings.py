import asyncio
import logging
import os
import sys
import types

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
    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    from app import embeddings

    monkeypatch.setattr(embeddings, "get_openai_client", lambda: DummyOpenAIClient())
    embeddings._embed_openai_sync.cache_clear()

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
    monkeypatch.setenv("EMBEDDING_BACKEND", "llama")
    monkeypatch.setenv("LLAMA_EMBEDDINGS_MODEL", "/tmp/model.gguf")
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
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
        monkeypatch.setenv("VECTOR_STORE", "chroma")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr(embeddings, "get_openai_client", lambda: DummyOpenAIClient())
        embeddings._embed_openai_sync.cache_clear()
        asyncio.run(embeddings.embed("hi"))
    elif backend == "llama":
        monkeypatch.setenv("EMBEDDING_BACKEND", "llama")
        monkeypatch.setenv("LLAMA_EMBEDDINGS_MODEL", "/tmp/model.gguf")
        monkeypatch.setenv("VECTOR_STORE", "chroma")
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setattr(embeddings, "Llama", lambda *a, **k: DummyLlama())
        embeddings._llama_model = None
        asyncio.run(embeddings.embed("hi"))
    else:
        monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
        embeddings.embed_sync("hi")
    assert f"backend={backend}" in caplog.text


@pytest.mark.parametrize("func", ["embed_sync", "embed"])
def test_force_stub_pytest(monkeypatch, func):
    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")
    from app import embeddings

    def boom():
        raise RuntimeError("should not call openai")

    monkeypatch.setattr(embeddings, "get_openai_client", boom)
    expected = embeddings._embed_stub("hi")
    if func == "embed_sync":
        res = embeddings.embed_sync("hi")
    else:
        res = asyncio.run(embeddings.embed("hi"))
    assert res == expected


@pytest.mark.parametrize("func", ["embed_sync", "embed"])
def test_force_stub_memory(monkeypatch, func):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("VECTOR_STORE", "memory")
    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")
    from app import embeddings

    def boom():
        raise RuntimeError("should not call openai")

    monkeypatch.setattr(embeddings, "get_openai_client", boom)
    expected = embeddings._embed_stub("hi")
    if func == "embed_sync":
        res = embeddings.embed_sync("hi")
    else:
        res = asyncio.run(embeddings.embed("hi"))
    assert res == expected


def test_openai_cache_ttl(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")
    from app import embeddings

    class DummyClient:
        def __init__(self):
            self.calls = 0
            self.embeddings = self

        def create(self, model, input, encoding_format="float"):
            self.calls += 1
            return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.0] * 8)])

    dummy = DummyClient()
    monkeypatch.setattr(embeddings, "get_openai_client", lambda: dummy)
    embeddings._embed_openai_sync.cache_clear()
    monkeypatch.setattr(embeddings, "_TTL", 1)
    t = 0

    def fake_time():
        return t

    monkeypatch.setattr(embeddings.time, "time", fake_time)

    asyncio.run(embeddings.embed("hi"))
    asyncio.run(embeddings.embed("hi"))
    assert dummy.calls == 1

    t = 2
    asyncio.run(embeddings.embed("hi"))
    assert dummy.calls == 2


def test_llama_missing_dependency(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    monkeypatch.setenv("EMBEDDING_BACKEND", "llama")
    from app import embeddings

    monkeypatch.setattr(embeddings, "Llama", None)
    embeddings._llama_model = None
    with pytest.raises(RuntimeError) as exc:
        embeddings.embed_sync("hi")
    assert "llama-cpp-python not installed" in str(exc.value)


def test_llama_missing_model(monkeypatch):
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("VECTOR_STORE", "chroma")
    monkeypatch.setenv("EMBEDDING_BACKEND", "llama")
    from app import embeddings

    monkeypatch.setattr(embeddings, "Llama", lambda *a, **k: DummyLlama())
    monkeypatch.delenv("LLAMA_EMBEDDINGS_MODEL", raising=False)
    embeddings._llama_model = None
    with pytest.raises(RuntimeError) as exc:
        embeddings.embed_sync("hi")
    assert "Missing LLAMA_EMBEDDINGS_MODEL" in str(exc.value)


def test_stub_deterministic(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    from app import embeddings

    v1 = embeddings.embed_sync("hello")
    v2 = embeddings.embed_sync("hello")
    v3 = asyncio.run(embeddings.embed("hello"))
    assert len(v1) == 8
    assert v1 == v2 == v3
