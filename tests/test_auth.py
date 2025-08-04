import sys
from importlib import import_module

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt


def _client(monkeypatch):
    monkeypatch.setenv("LOGIN_USERS", '{"alice": "wonderland"}')
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "5")
    sys.modules.pop("app.auth", None)
    auth = import_module("app.auth")
    app = FastAPI()
    app.include_router(auth.router)
    return TestClient(app)


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
