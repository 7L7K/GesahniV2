def test_get_config_pytest_flag(monkeypatch):
    from app import config_runtime as cr

    # ensure test mode path is used
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    monkeypatch.setenv("VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "http://qdrant")
    cfg = cr.get_config()
    assert cfg.store.vector_store == "qdrant"
    assert cfg.store.qdrant_url == "http://qdrant"


