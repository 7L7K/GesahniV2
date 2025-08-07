import importlib

from app.memory import vector_store


def test_get_store_falls_back_to_memory(monkeypatch, tmp_path):
    # create a file path that cannot be used as a directory
    bad_file = tmp_path / "not_a_dir"
    bad_file.write_text("x")
    monkeypatch.setenv("CHROMA_PATH", str(bad_file))
    # Ensure default vector store path attempts chroma
    monkeypatch.delenv("VECTOR_STORE", raising=False)

    # Reload the module so _get_store uses the new CHROMA_PATH
    module = importlib.reload(vector_store)

    # Stub out embedding to avoid external dependencies during the test
    monkeypatch.setattr(module, "embed_sync", lambda text: [0.0])

    store = module._get_store()
    assert isinstance(store, module.MemoryVectorStore)
    store._dist_cutoff = 1.0

    # Ensure basic operations work without raising
    store.add_user_memory("u", "hello")
    assert store.query_user_memories("u", "hello") == ["hello"]
