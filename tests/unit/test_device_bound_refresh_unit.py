import os
from importlib import import_module

from fastapi.testclient import TestClient


def _client(monkeypatch):
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    monkeypatch.setenv("JWT_SECRET", "s")
    # Fresh import of auth to ensure router uses a clean in-memory revocation set
    auth = import_module("app.auth")
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(auth.router, prefix="/v1")
    client = TestClient(app)
    client.post("/v1/register", json={"username": "a1", "password": "secret123"})
    r = client.post("/v1/login", json={"username": "a1", "password": "secret123"})
    assert r.status_code == 200
    tokens = r.json()
    return client, tokens


def test_refresh_single_use_revokes(monkeypatch):
    c, t = _client(monkeypatch)
    r1 = c.post("/v1/refresh", json={"refresh_token": t["refresh_token"]})
    assert r1.status_code == 200
    # Using the same refresh again should fail (revoked)
    r2 = c.post("/v1/refresh", json={"refresh_token": t["refresh_token"]})
    assert r2.status_code == 401


