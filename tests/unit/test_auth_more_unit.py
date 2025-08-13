import os
import sys
import tempfile
import sqlite3

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


def _client(monkeypatch):
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    monkeypatch.setenv("USERS_DB", db_path)
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "5")
    sys.modules.pop("app.auth", None)
    from importlib import import_module

    auth = import_module("app.auth")
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)
    client.post("/register", json={"username": "alice", "password": "wonderland"})
    return client


def test_login_unknown_hash_returns_401(monkeypatch):
    client = _client(monkeypatch)
    # Corrupt the stored hash with an unknown scheme
    db_path = os.environ["USERS_DB"]
    with sqlite3.connect(db_path) as db:
        db.execute("UPDATE auth_users SET password_hash=? WHERE username=?", ("md5$deadbeef", "alice"))
        db.commit()
    r = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert r.status_code == 401


def test_password_strength_enforced_when_env_set(monkeypatch):
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    monkeypatch.setenv("USERS_DB", db_path)
    monkeypatch.setenv("JWT_SECRET", "s")
    monkeypatch.setenv("PASSWORD_STRENGTH", "1")
    sys.modules.pop("app.auth", None)
    from importlib import import_module

    auth = import_module("app.auth")
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)
    # Too weak under PASSWORD_STRENGTH=1
    r = client.post("/register", json={"username": "bob", "password": "secret"})
    assert r.status_code == 400


def test_refresh_uses_cookie_when_body_missing(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert r.status_code == 200
    # Cookies persisted in client are used by /refresh without body
    r2 = client.post("/refresh")
    assert r2.status_code == 200


def test_register_username_taken(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/register", json={"username": "alice", "password": "wonderland2"})
    assert r.status_code == 400


def test_logout_invalid_token_returns_401(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/logout", headers={"Authorization": "Bearer notatoken"})
    assert r.status_code == 401


