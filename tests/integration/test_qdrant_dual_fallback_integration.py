def test_vector_store_selection_env(monkeypatch):
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    monkeypatch.setenv("ALLOW_QDRANT_IN_TESTS", "1")
    from importlib import reload
    from unittest.mock import Mock

    # Mock the QdrantClient to avoid connection errors
    mock_client = Mock()
    mock_client.get_collections.return_value = []
    mock_client.recreate_collection.return_value = None
    mock_client.get_collection.return_value = Mock(points_count=0)

    # Reload the qdrant module to pick up the ALLOW_QDRANT_IN_TESTS setting
    import app.memory.vector_store.qdrant as qdrant_mod

    reload(qdrant_mod)

    # Patch QdrantClient before importing memory api
    with monkeypatch.context() as m:
        m.setattr(
            "app.memory.vector_store.qdrant.QdrantClient",
            lambda *args, **kwargs: mock_client,
        )

        import app.memory.api as mem

        reload(mem)
        store = mem.get_store()
        # Test Qdrant selection when enabled
        assert type(store).__name__.lower() in {"qdrantvectorstore"}


def test_dual_mode_logs(monkeypatch, caplog):
    monkeypatch.setenv("VECTOR_STORE", "dual")
    monkeypatch.setenv("ALLOW_QDRANT_IN_TESTS", "1")
    from importlib import reload
    from unittest.mock import Mock

    # Mock the QdrantClient to avoid connection errors
    mock_client = Mock()
    mock_client.get_collections.return_value = []
    mock_client.recreate_collection.return_value = None
    mock_client.get_collection.return_value = Mock(points_count=0)
    mock_client.scroll.return_value = ([], None)
    mock_client.search.return_value = []
    mock_client.upsert.return_value = Mock(operation_id="test-op")
    mock_client.delete.return_value = None
    mock_client.delete_collection.return_value = None

    # Reload the qdrant module to pick up the ALLOW_QDRANT_IN_TESTS setting
    import app.memory.vector_store.qdrant as qdrant_mod

    reload(qdrant_mod)

    # Patch QdrantClient before importing memory api
    with monkeypatch.context() as m:
        m.setattr(
            "app.memory.vector_store.qdrant.QdrantClient",
            lambda *args, **kwargs: mock_client,
        )

        import app.memory.api as mem

        reload(mem)
        store = mem.get_store()
        # Should initialize a DualReadVectorStore
        assert "dual" in type(store).__name__.lower()
