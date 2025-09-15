import pytest
from fastapi.testclient import TestClient


def make_app(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    from app.main import app

    return app


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setenv(
        "JWT_SECRET", "admin_guardrails_secret_abcdefghijklmnopqrstuvwxyz123456"
    )


def mint(scopes=None):
    from app.tokens import make_access

    claims = {"user_id": "u_adm"}
    if scopes is not None:
        claims["scopes"] = scopes
    return make_access(claims)


def test_guard_unauthenticated_is_401(monkeypatch):
    # Disable CSRF to test auth failure directly (CSRF happens first when enabled)
    app = make_app(monkeypatch, CSRF_ENABLED="0")
    client = TestClient(app)
    r = client.post("/v1/ask", json={"prompt": "hi"})
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_guard_missing_scope_is_403(monkeypatch):
    # Disable CSRF to surface scope failure deterministically
    app = make_app(monkeypatch, CSRF_ENABLED="0")
    client = TestClient(app)
    token = mint(["music:control"])  # missing chat:write
    r = client.post(
        "/v1/ask",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"prompt": "hi"},
    )
    assert r.status_code == 403


def test_guard_success_with_csrf_cookie_and_header(monkeypatch):
    app = make_app(monkeypatch, CSRF_ENABLED="1")
    client = TestClient(app)
    token = mint(["admin:write"])  # sufficient scope for /v1/admin/config/test
    csrf = "csrf-admin-token"
    r = client.post(
        "/v1/admin/config/test",
        headers={
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": csrf,
            "Content-Type": "application/json",
        },
        cookies={"csrf_token": csrf},
        json={},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
