import importlib

import pytest
from fastapi.testclient import TestClient


def _reload_app():
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    import app.main as main
    return main


def test_dev_weak_secret_allows(monkeypatch):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("DEV_MODE", "1")
    monkeypatch.setenv("JWT_SECRET", "short")
    main = _reload_app()
    with TestClient(main.app) as c:
        r = c.get("/")
        assert r.status_code in (200, 404, 405)


def test_prod_weak_secret_rejects(monkeypatch):
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.setenv("JWT_SECRET", "short")

    # Force module reload to get fresh environment
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]

    # Import the module to trigger import-time checks
    import app.main

    # Manually call the JWT enforcement function that should raise
    with pytest.raises(RuntimeError):
        app.main._enforce_jwt_strength()


