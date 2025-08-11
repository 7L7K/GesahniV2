from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_admin_routes_denied_without_scope(monkeypatch):
    client = TestClient(app)
    # No admin token + no JWT => scopes off; but router requires admin scope; we expect 401/403 when JWT enforced
    # Simulate scopes enforcement by setting ENFORCE_JWT_SCOPES and JWT_SECRET and stubbing state
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    monkeypatch.setenv("JWT_SECRET", "x")
    r = client.get("/v1/admin/config", headers={"Authorization": "Bearer invalid"})
    assert r.status_code in {401, 403}


def test_pin_requires_scope_when_enforced(monkeypatch):
    # With scopes enforced and no 'pin' scope, pin endpoint should 403/401
    client = TestClient(app)
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    monkeypatch.setenv("JWT_SECRET", "x")
    r = client.post("/v1/history/pin", params={"session_id": "s", "hash_value": "h"}, headers={"Authorization": "Bearer invalid"})
    assert r.status_code in {401, 403}


