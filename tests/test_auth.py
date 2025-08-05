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
    resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    payload = jwt.decode(token, "testsecret", algorithms=["HS256"])
    assert payload["sub"] == "alice"
    assert "exp" in payload


def test_login_bad_credentials(monkeypatch):
    client = _client(monkeypatch)
    resp = client.post("/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401


def test_login_sets_user_id(monkeypatch):
    client = _client(monkeypatch)

    captured: dict[str, str] = {}

    def fake_user_id(request: Request) -> str:
        request.state.user_id = "abc"
        captured["user_id"] = request.state.user_id
        return "abc"

    client.app.dependency_overrides[get_current_user_id] = fake_user_id

    resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert resp.status_code == 200
    assert captured["user_id"] == "abc"
