import importlib


def test_qdrant_disabled_in_pytest_by_default(monkeypatch):
    # Ensure default behavior disables qdrant under pytest
    monkeypatch.delenv("ALLOW_QDRANT_IN_TESTS", raising=False)
    import app.memory.vector_store.qdrant as q
    importlib.reload(q)
    assert getattr(q, "QdrantClient", None) is None


