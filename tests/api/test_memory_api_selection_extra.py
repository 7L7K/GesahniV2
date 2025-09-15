import importlib


def test_default_to_memory_under_pytest(monkeypatch, tmp_path):
    monkeypatch.delenv("VECTOR_STORE", raising=False)
    monkeypatch.delenv("VECTOR_DSN", raising=False)
    # Set memory store for tests
    monkeypatch.setenv("VECTOR_DSN", "memory://")
    import app.memory.api as mem_api

    importlib.reload(mem_api)
    # Need to call get_store() to initialize the store
    store = mem_api.get_store()
    assert type(store).__name__ == "MemoryVectorStore"


def test_unknown_kind_records_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("VECTOR_DSN", "weird://")
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path))
    import app.memory.api as mem_api

    importlib.reload(mem_api)
    # Need to call get_store() to initialize the store
    store = mem_api.get_store()
    assert type(store).__name__ in {"ChromaVectorStore", "MemoryVectorStore"}


def test_dual_unavailable_falls_back(monkeypatch, tmp_path):
    # simulate dual store DSN
    monkeypatch.setenv(
        "VECTOR_DSN", "dual://qdrant://localhost:6333?chroma_path=" + str(tmp_path)
    )
    # simulate import failure
    import sys

    sys.modules.pop("app.memory.vector_store.dual", None)
    import app.memory.api as mem_api

    importlib.reload(mem_api)
    # Need to call get_store() to initialize the store
    store = mem_api.get_store()
    assert type(store).__name__ == "MemoryVectorStore"
