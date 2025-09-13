import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient


@contextmanager
def env(**kwargs):
    old = {k: os.environ.get(k) for k in kwargs}
    try:
        for k, v in kwargs.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _build_app():
    # Import inside to pick up env for create_app()
    from app.main import create_app

    return create_app()


def _middleware_names(app):
    return [m.cls.__name__ for m in app.user_middleware]


def test_no_cors_in_proxy_mode():
    # No CORS origins configured → no CORSMiddleware expected (proxy/same-origin dev)
    with env(CORS_ORIGINS=None, CORS_ALLOW_ORIGINS=None, DEV_MODE=1):
        app = _build_app()
        mids = _middleware_names(app)
        assert mids.count("CORSMiddleware") == 0, mids
        # Ensure custom CORS layers are not present
        assert "CorsPreflightMiddleware" not in mids
        assert "SafariCORSCacheFixMiddleware" not in mids


def test_single_cors_when_configured():
    # Explicit CORS origins configured → one CORSMiddleware present
    with env(CORS_ALLOW_ORIGINS="http://localhost:3000"):
        app = _build_app()
        mids = _middleware_names(app)
        assert mids.count("CORSMiddleware") == 1, mids
        assert "CorsPreflightMiddleware" not in mids
        assert "SafariCORSCacheFixMiddleware" not in mids


def test_cookie_roundtrip_login_whoami(tmp_path, monkeypatch):
    # Ensure cookie roundtrip works without CORS in proxy mode
    with env(CORS_ALLOW_ORIGINS=None, COOKIE_SAMESITE="lax", COOKIE_SECURE=0, DEV_MODE=1, JWT_SECRET="secret-secret-123456"):
        app = _build_app()
        client = TestClient(app)

        # Login to set cookies
        r = client.post("/v1/auth/login", params={"username": "playwright"})
        assert r.status_code == 200
        # Cookies should be in the client cookie jar now
        assert any(c.name for c in client.cookies.jar if c.name)

        # Whoami should reflect authenticated state
        r2 = client.get("/v1/whoami")
        assert r2.status_code == 200
        body = r2.json()
        # Accept either canonical keys or fallback shape but must be authed
        assert body.get("is_authenticated") is True or body.get("authenticated") is True

