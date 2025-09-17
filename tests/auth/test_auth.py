import os
import sys
import tempfile
from importlib import import_module

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt

from app.deps.user import get_current_user_id


def _client(monkeypatch):
    """Create a test client with database initialization."""
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    monkeypatch.setenv("USERS_DB", db_path)
    monkeypatch.setenv("JWT_SECRET", "x" * 64)  # 64 character secret for testing
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "60")  # Use long TTL for testing
    monkeypatch.setenv("CSRF_ENABLED", "0")  # Disable CSRF for tests
    monkeypatch.setenv("DEV_AUTH", "1")  # Enable dev auth router

    # Initialize database tables
    import asyncio

    from app.db import init_db_once

    asyncio.run(init_db_once())

    sys.modules.pop("app.auth", None)
    auth = import_module("app.auth")
    app = FastAPI()
    app.include_router(auth.router)

    # Include dev auth router for testing
    try:
        from app.api.auth_router_dev import router as dev_auth_router

        app.include_router(dev_auth_router, prefix="/v1")
    except ImportError:
        pass  # Dev auth router not available
    client = TestClient(app)
    client.post("/v1/auth/register", json={"username": "test_user_123"})
    return client


def test_login_success(monkeypatch):
    client = _client(monkeypatch)

    def fake_user_id(request: Request) -> str:
        request.state.user_id = "abc"
        return "abc"

    client.app.dependency_overrides[get_current_user_id] = fake_user_id

    resp = client.post("/v1/auth/dev/login", json={"username": "test_user_123"})
    assert resp.status_code == 200
    data = resp.json()

    # New shape: access_token + refresh_token
    token = data["access_token"]
    refresh = data["refresh_token"]

    payload = jwt.decode(token, "testsecret", algorithms=["HS256"])
    assert payload["sub"] == "test_user_123"
    assert payload["type"] == "access"

    payload_r = jwt.decode(refresh, "testsecret", algorithms=["HS256"])
    assert payload_r["type"] == "refresh"


def test_login_bad_credentials(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post(
        "/v1/auth/dev/login", json={"username": "test_user_123", "password": "wrong"}
    )
    assert resp.status_code == 401


def test_login_is_public_endpoint(monkeypatch):
    """Test that login endpoint is public and doesn't require authentication."""
    client = _client(monkeypatch)

    # Login should work without any authentication
    resp = client.post("/v1/auth/dev/login", json={"username": "test_user_123"})
    assert resp.status_code == 200
    data = resp.json()

    # Verify tokens are returned
    assert "access_token" in data
    assert "refresh_token" in data

    # Verify token contents
    token = data["access_token"]
    refresh = data["refresh_token"]

    payload = jwt.decode(token, "testsecret", algorithms=["HS256"])
    assert payload["sub"] == "test_user_123"
    assert payload["type"] == "access"

    payload_r = jwt.decode(refresh, "testsecret", algorithms=["HS256"])
    assert payload_r["type"] == "refresh"


def test_refresh_and_logout(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/v1/auth/dev/login", json={"username": "test_user_123"})
    tokens = resp.json()
    refresh = tokens["refresh_token"]

    # Set refresh token as cookie for refresh endpoint
    client.cookies.set("GSNH_RT", refresh)

    # Refresh should succeed once
    r2 = client.post("/v1/auth/refresh")
    assert r2.status_code == 200
    new_tokens = r2.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens

    # Update cookie with new refresh token for logout test
    latest_refresh = new_tokens["refresh_token"]
    client.cookies.set("GSNH_RT", latest_refresh)

    # Test logout functionality (this should definitely invalidate the token)
    # Note: Due to test-friendly replay protection, old tokens may work briefly
    # But logout should definitely invalidate them
    r3 = client.post(
        "/v1/auth/logout", headers={"Authorization": f"Bearer {latest_refresh}"}
    )
    assert r3.status_code == 204

    # Token cannot be used after logout - set latest token
    client.cookies.set("GSNH_RT", latest_refresh)
    r4 = client.post("/v1/auth/refresh")
    assert r4.status_code == 401
