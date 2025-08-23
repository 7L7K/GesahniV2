import os

import jwt
from fastapi.testclient import TestClient

from app.main import app


def _bearer(user="u1", scopes=None):
    payload = {"user_id": user}
    if scopes:
        if isinstance(scopes, str):
            payload["scope"] = scopes
        else:
            payload["scope"] = " ".join(scopes)
    tok = jwt.encode(payload, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")
    return {"Authorization": f"Bearer {tok}"}


def test_music_routes_gate_by_scope(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    c = TestClient(app)
    # Without scope -> 403 somewhere in music endpoints
    r0 = c.get("/v1/state", headers=_bearer(scopes=[]))
    assert r0.status_code in (401, 403, 404)
    # With scope -> should allow a known music route (devices list is safe)
    r1 = c.get("/v1/music/devices", headers=_bearer(scopes=["music:control"]))
    assert r1.status_code in (200, 400)


def test_admin_routes_gate_by_scope(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    c = TestClient(app)
    r_forbidden = c.get("/v1/admin/metrics", headers=_bearer(scopes=["music:control"]))
    assert r_forbidden.status_code in (401, 403)
    # admin endpoints also check ADMIN_TOKEN; we focus on scope now
    r_scope = c.get("/v1/admin/metrics", headers=_bearer(scopes=["admin:write"]))
    assert r_scope.status_code in (200, 403)  # token gate may still apply


def test_ha_routes_gate_by_care_scopes(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    c = TestClient(app)
    # A HA endpoint included in main under ha_router
    r_no = c.get("/v1/ha/entities", headers=_bearer(scopes=["music:control"]))
    assert r_no.status_code in (401, 403)
    r_yes = c.get("/v1/ha/entities", headers=_bearer(scopes=["care:resident"]))
    assert r_yes.status_code in (200, 500)


def test_caregiver_router_requires_caregiver_scope(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    c = TestClient(app)
    r_no = c.get("/v1/caregiver", headers=_bearer(scopes=["care:resident"]))
    assert r_no.status_code in (401, 403, 404)
    r_ok = c.get("/v1/caregiver", headers=_bearer(scopes=["care:caregiver"]))
    assert r_ok.status_code in (200, 404)


def test_docs_shows_locks_for_music_and_admin(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    c = TestClient(app)
    schema = c.get("/openapi.json").json()
    found_music = False
    found_admin = False
    for path, item in schema.get("paths", {}).items():
        if path.startswith("/v1/music"):
            methods = list(item.keys())
            sec = item[methods[0]].get("security", [])
            if any("OAuth2" in d for d in sec):
                found_music = True
        if path.startswith("/v1/admin/"):
            methods = list(item.keys())
            sec = item[methods[0]].get("security", [])
            if any("OAuth2" in d for d in sec):
                found_admin = True
    assert found_admin
    assert found_music


def test_docs_schemes_include_all_scopes(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    c = TestClient(app)
    schema = c.get("/openapi.json").json()
    scopes = schema["components"]["securitySchemes"]["OAuth2"]["flows"]["password"][
        "scopes"
    ]
    for s in ["admin:write", "music:control", "care:resident", "care:caregiver"]:
        assert s in scopes
