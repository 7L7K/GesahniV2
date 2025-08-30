import importlib

from app.memory import unified_store


def test_get_store_falls_back_to_memory(monkeypatch):
    # Test fallback when an unsupported scheme is used
    monkeypatch.setenv("VECTOR_DSN", "unsupported://bad-scheme")
    monkeypatch.delenv("VECTOR_STORE", raising=False)

    # Reload the module to pick up changes
    module = importlib.reload(unified_store)

    # This should fall back to MemoryVectorStore due to the unsupported scheme
    store = module.create_vector_store()
    assert isinstance(store, module.MemoryVectorStore)

    # Ensure basic operations work without raising
    store.add_user_memory("u", "hello")
    assert store.query_user_memories("u", "hello") == ["hello"]
