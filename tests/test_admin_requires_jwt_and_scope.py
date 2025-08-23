import os

import jwt
from fastapi.testclient import TestClient


def _client(monkeypatch):
    os.environ["ADMIN_TOKEN"] = "t"
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    from app.main import app
    return TestClient(app)


def _tok(scopes: str = ""):
    payload = {"user_id": "admin"}
    if scopes:
        payload["scope"] = scopes
    return jwt.encode(payload, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")


def test_admin_denies_without_jwt(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    c = _client(monkeypatch)
    # Missing Authorization header → 401
    r = c.get("/v1/admin/config", params={"token": "t"})
    assert r.status_code == 401


def test_admin_requires_scope_with_jwt(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    # Enforce scopes to ensure optional check is active
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    c = _client(monkeypatch)
    # With JWT but no admin scope → 403
    r = c.get("/v1/admin/config", params={"token": "t"}, headers={"Authorization": f"Bearer {_tok('')}"})
    assert r.status_code in {401, 403}
    # With admin scope → 200
    r2 = c.get("/v1/admin/config", params={"token": "t"}, headers={"Authorization": f"Bearer {_tok('admin:write')}"})
    assert r2.status_code == 200


