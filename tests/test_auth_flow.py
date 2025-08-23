import importlib
import os
import tempfile

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_login_throttling(monkeypatch):
    os.environ["LOGIN_ATTEMPT_MAX"] = "2"
    os.environ["LOGIN_ATTEMPT_WINDOW_SECONDS"] = "60"
    # use isolated temp db
    fd, db_path = tempfile.mkstemp()
    os.close(fd)
    monkeypatch.setenv("USERS_DB", db_path)
    from app import auth

    importlib.reload(auth)
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)

    # Register a user
    r = client.post("/register", json={"username": "user1", "password": "secret"})
    assert r.status_code == 200

    # Two bad attempts
    assert client.post("/login", json={"username": "user1", "password": "bad"}).status_code == 401
    assert client.post("/login", json={"username": "user1", "password": "bad"}).status_code == 401
    # Third should be 429 with retry_after
    rr = client.post("/login", json={"username": "user1", "password": "bad"})
    assert rr.status_code == 429
    body = rr.json()
    assert "retry_after" in body.get("detail", {})


def test_password_reset(monkeypatch):
    # use isolated temp db
    fd, db_path = tempfile.mkstemp()
    os.close(fd)
    monkeypatch.setenv("USERS_DB", db_path)
    from app import auth
    importlib.reload(auth)
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)

    # Register
    assert client.post("/register", json={"username": "resetme", "password": "secret"}).status_code == 200
    # Request reset token (in tests returns token)
    fr = client.post("/forgot", json={"username": "resetme"})
    tok = fr.json().get("token")
    assert tok
    # Apply reset
    rr = client.post("/reset_password", json={"token": tok, "new_password": "secret99"})
    assert rr.status_code == 200
    # Can login with new password
    ok = client.post("/login", json={"username": "resetme", "password": "secret99"})
    assert ok.status_code == 200

