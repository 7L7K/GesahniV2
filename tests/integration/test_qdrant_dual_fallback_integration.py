def test_vector_store_selection_env(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    from importlib import reload

    import app.memory.api as mem

    reload(mem)
    store = mem.get_store()
    # Name-based check to avoid imports of optional deps in CI
    assert type(store).__name__.lower() in {"qdrantvectorstore"}


def test_dual_mode_logs(monkeypatch, caplog):
    monkeypatch.setenv("VECTOR_STORE", "dual")
    from importlib import reload

    import app.memory.api as mem

    reload(mem)
    store = mem.get_store()
    # Should initialize a DualReadVectorStore
    assert "dual" in type(store).__name__.lower()
