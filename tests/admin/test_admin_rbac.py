# tests/test_admin_rbac.py
import importlib
import os
import time

import jwt
from starlette.testclient import TestClient


def _spin():
    """Fresh app instance for testing with JWT secret."""
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    # Set a strong JWT secret for testing
    os.environ["JWT_SECRET"] = "x" * 64
    # Enable admin routes for testing
    os.environ["ENV"] = "dev"
    os.environ["ENABLE_ADMIN_ROUTES"] = "true"
    from app.main import app

    return TestClient(app)


def _tok(scopes=None):
    key = os.environ.get("JWT_SECRET", "x" * 64)
    now = int(time.time())
    payload = {"sub": "u1", "iat": now, "exp": now + 60}
    if scopes:
        payload["scopes"] = scopes
    return jwt.encode(payload, key, algorithm="HS256")


def test_admin_unauth():
    client = _spin()
    r = client.get("/v1/admin/ping")
    assert r.status_code == 401


def test_admin_forbidden():
    client = _spin()
    r = client.get(
        "/v1/admin/ping", headers={"Authorization": f"Bearer {_tok(['user'])}"}
    )
    assert r.status_code == 403


def test_admin_ok():
    client = _spin()
    r = client.get(
        "/v1/admin/ping", headers={"Authorization": f"Bearer {_tok(['admin'])}"}
    )
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_admin_rbac_info_unauth():
    client = _spin()
    r = client.get("/v1/admin/rbac/info")
    assert r.status_code == 401


def test_admin_rbac_info_forbidden():
    client = _spin()
    r = client.get(
        "/v1/admin/rbac/info", headers={"Authorization": f"Bearer {_tok(['user'])}"}
    )
    assert r.status_code == 403


def test_admin_rbac_info_ok():
    client = _spin()
    r = client.get(
        "/v1/admin/rbac/info",
        headers={"Authorization": f"Bearer {_tok(['admin:read'])}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "scopes_available" in data
    assert "user_scopes" in data


def test_admin_users_me_unauth():
    client = _spin()
    r = client.get("/v1/admin/users/me")
    assert r.status_code == 401


def test_admin_users_me_ok():
    client = _spin()
    r = client.get(
        "/v1/admin/users/me",
        headers={"Authorization": f"Bearer {_tok(['user:profile'])}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "user_id" in data
    assert "scopes" in data


def test_admin_system_status_unauth():
    client = _spin()
    r = client.get("/v1/admin/system/status")
    assert r.status_code == 401


def test_admin_system_status_forbidden():
    client = _spin()
    r = client.get(
        "/v1/admin/system/status", headers={"Authorization": f"Bearer {_tok(['user'])}"}
    )
    assert r.status_code == 403


def test_admin_system_status_ok():
    client = _spin()
    r = client.get(
        "/v1/admin/system/status",
        headers={"Authorization": f"Bearer {_tok(['admin:read'])}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "environment" in data
