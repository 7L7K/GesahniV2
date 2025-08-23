import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_get_csrf_sets_cookie_and_returns_token():
    c = TestClient(app)
    r = c.get("/v1/csrf")
    assert r.status_code == 200
    assert "csrf_token" in r.json()
    sc = r.headers.get("set-cookie", "")
    assert "csrf_token=" in sc
    assert "Path=/" in sc
    assert "SameSite=" in sc


def test_csrf_cookie_flags_respect_env():
    # Test default (dev) behavior first
    with TestClient(app) as c:
        r = c.get("/v1/csrf")
        sc = r.headers.get("set-cookie", "")
        # In dev mode, should be Lax by default
        assert "SameSite=Lax" in sc or "SameSite=lax" in sc

    # Test cross-site production configuration
    with patch.dict(
        os.environ, {"COOKIE_SAMESITE": "none", "COOKIE_SECURE": "1", "DEV_MODE": "0"}
    ):
        # Import and patch the configuration functions directly
        # Reload the modules to pick up new environment variables
        from importlib import reload

        import app.cookie_config as cookie_cfg
        import app.cookies as cookies_mod

        reload(cookie_cfg)
        reload(cookies_mod)

        with TestClient(app) as c:
            r = c.get("/v1/csrf")
            sc = r.headers.get("set-cookie", "")
            assert "SameSite=None" in sc
            assert "Secure" in sc
