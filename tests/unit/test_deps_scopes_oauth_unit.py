import os

import jwt
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.deps.scopes import (
    OAUTH2_SCOPES,
    docs_security_with,
    optional_require_any_scope,
    optional_require_scope,
    require_any_scope,
)


def _make_token(scopes=None) -> str:
    payload = {"user_id": "u1"}
    if scopes:
        if isinstance(scopes, (list, tuple, set)):
            payload["scope"] = " ".join(sorted(set(scopes)))
        else:
            payload["scope"] = str(scopes)
    tok = jwt.encode(payload, os.getenv("JWT_SECRET", "secret"), algorithm="HS256")
    return f"Bearer {tok}"


def test_openapi_includes_oauth2_security_scheme(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    app = FastAPI()

    @app.get("/secure", dependencies=[Depends(docs_security_with(["admin:write"]))])
    async def secure():
        return {"ok": True}

    schema = app.openapi()
    comps = schema.get("components", {}).get("securitySchemes", {})
    assert "OAuth2" in comps
    oauth = comps["OAuth2"]
    assert oauth.get("type") == "oauth2"
    flows = oauth.get("flows", {})
    assert "password" in flows
    assert flows["password"].get("tokenUrl", "").endswith("/auth/token")
    scopes = flows["password"].get("scopes", {})
    assert "admin:write" in scopes


def test_require_any_scope_allows_when_present(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    app = FastAPI()

    @app.get("/any", dependencies=[Depends(require_any_scope(["a", "b"]))])
    async def handler():
        return {"ok": True}

    c = TestClient(app)
    h = {"Authorization": _make_token(["b"])}
    assert c.get("/any", headers=h).status_code == 200


def test_require_any_scope_blocks_when_missing(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    app = FastAPI()

    @app.get("/any", dependencies=[Depends(require_any_scope(["a", "b"]))])
    async def handler():
        return {"ok": True}

    c = TestClient(app)
    h = {"Authorization": _make_token(["c"])}
    assert c.get("/any", headers=h).status_code == 403


def test_optional_require_any_scope_noop_when_env_not_set(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.delenv("ENFORCE_JWT_SCOPES", raising=False)
    app = FastAPI()

    @app.get("/opt-any", dependencies=[Depends(optional_require_any_scope(["a"]))])
    async def handler():
        return {"ok": True}

    c = TestClient(app)
    # No auth header should still pass because enforcement not enabled
    assert c.get("/opt-any").status_code == 200


def test_optional_require_scope_enforces_when_enabled(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "secret")
    monkeypatch.setenv("ENFORCE_JWT_SCOPES", "1")
    app = FastAPI()

    @app.get("/opt", dependencies=[Depends(optional_require_scope("admin:write"))])
    async def handler():
        return {"ok": True}

    c = TestClient(app)
    # Missing -> 401 because verify payload not attached (tokenless)
    r0 = c.get("/opt")
    assert r0.status_code in (401, 403)
    # Wrong scopes -> 403
    h_bad = {"Authorization": _make_token(["music:control"])}
    assert c.get("/opt", headers=h_bad).status_code == 403
    # Correct -> 200
    h_ok = {"Authorization": _make_token(["admin:write"])}
    assert c.get("/opt", headers=h_ok).status_code == 200


def test_docs_security_with_runtime_noop(monkeypatch):
    # Should not block requests even with JWT_SECRET present, since it's docs-only
    monkeypatch.setenv("JWT_SECRET", "secret")
    app = FastAPI()

    @app.get(
        "/docs-bound", dependencies=[Depends(docs_security_with(["music:control"]))]
    )
    async def handler():
        return {"ok": True}

    c = TestClient(app)
    assert c.get("/docs-bound").status_code == 200


def test_oauth2_scopes_mapping_contains_expected_keys():
    for k in ["care:resident", "care:caregiver", "music:control", "admin:write"]:
        assert k in OAUTH2_SCOPES
