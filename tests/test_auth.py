import os
import sys
import tempfile
from importlib import import_module

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt

from app.deps.user import get_current_user_id


def _client(monkeypatch):
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    monkeypatch.setenv("USERS_DB", db_path)
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "5")
    sys.modules.pop("app.auth", None)
    auth = import_module("app.auth")
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)
    client.post("/register", json={"username": "alice", "password": "wonderland"})
    return client


def test_login_success(monkeypatch):
    client = _client(monkeypatch)

    def fake_user_id(request: Request) -> str:
        request.state.user_id = "abc"
        return "abc"

    client.app.dependency_overrides[get_current_user_id] = fake_user_id

    resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert resp.status_code == 200
    data = resp.json()

    # New shape: access_token + refresh_token
    token = data["access_token"]
    refresh = data["refresh_token"]

    payload = jwt.decode(token, "testsecret", algorithms=["HS256"])
    assert payload["sub"] == "alice"
    assert payload["type"] == "access"

    payload_r = jwt.decode(refresh, "testsecret", algorithms=["HS256"])
    assert payload_r["type"] == "refresh"


def test_login_bad_credentials(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401


def test_login_is_public_endpoint(monkeypatch):
    """Test that login endpoint is public and doesn't require authentication."""
    client = _client(monkeypatch)

    # Login should work without any authentication
    resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert resp.status_code == 200
    data = resp.json()

    # Verify tokens are returned
    assert "access_token" in data
    assert "refresh_token" in data

    # Verify token contents
    token = data["access_token"]
    refresh = data["refresh_token"]

    payload = jwt.decode(token, "testsecret", algorithms=["HS256"])
    assert payload["sub"] == "alice"
    assert payload["type"] == "access"

    payload_r = jwt.decode(refresh, "testsecret", algorithms=["HS256"])
    assert payload_r["type"] == "refresh"


def test_refresh_and_logout(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    tokens = resp.json()
    refresh = tokens["refresh_token"]

    # Refresh should succeed once
    r2 = client.post("/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 200
    new_tokens = r2.json()
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens

    # Old refresh token is now invalid
    r3 = client.post("/refresh", json={"refresh_token": refresh})
    assert r3.status_code == 401

    # Logout with latest refresh token
    latest_refresh = new_tokens["refresh_token"]
    r4 = client.post("/logout", headers={"Authorization": f"Bearer {latest_refresh}"})
    assert r4.status_code == 204

    # Token cannot be used after logout
    r5 = client.post("/refresh", json={"refresh_token": latest_refresh})
    assert r5.status_code == 401
