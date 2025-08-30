import os
import json
import pytest
from fastapi.testclient import TestClient


def make_app(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    # Import after env config
    from app.main import app
    return app


def mint_token(scopes=None):
    from app.tokens import make_access
    claims = {"user_id": "u_test"}
    if scopes is not None:
        claims["scopes"] = scopes
    return make_access(claims)


@pytest.fixture(autouse=True)
def _ensure_jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-123")
    monkeypatch.setenv("PYTEST_RUNNING", "1")


def test_ask_requires_auth(monkeypatch):
    # No CSRF needed when no auth because dependency returns 401 first
    app = make_app(monkeypatch, CSRF_ENABLED="1")
    client = TestClient(app)
    r = client.post("/v1/ask", json={"prompt": "hi"})
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_ask_requires_scope(monkeypatch):
    # Disable CSRF to surface scope error deterministically
    app = make_app(monkeypatch, CSRF_ENABLED="0")
    client = TestClient(app)
    token = mint_token(scopes=["care:resident"])  # no chat:write
    r = client.post(
        "/v1/ask",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"prompt": "hi"},
    )
    assert r.status_code == 403
    body = r.json()
    assert body.get("code") == "forbidden"
    assert body.get("message") == "missing scope"
    assert body.get("hint") == "chat:write"


def test_ask_with_cookie_and_csrf(monkeypatch):
    app = make_app(monkeypatch, CSRF_ENABLED="1")
    client = TestClient(app)
    token = mint_token()  # defaults include chat:write
    csrf = "csrf-test-token"
    cookies = {
        "GSNH_AT": token,
        "csrf_token": csrf,
    }
    r = client.post(
        "/v1/ask",
        json={"prompt": "hi"},
        headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
        cookies=cookies,
    )
    assert r.status_code == 200


def test_ask_with_bearer_and_csrf(monkeypatch):
    app = make_app(monkeypatch, CSRF_ENABLED="1")
    client = TestClient(app)
    token = mint_token()  # defaults include chat:write
    csrf = "csrf-bearer"
    # Even for bearer, our endpoint dependency enforces CSRF when enabled
    r = client.post(
        "/v1/ask",
        json={"prompt": "hi"},
        headers={
            "Authorization": f"Bearer {token}",
            "X-CSRF-Token": csrf,
            "Content-Type": "application/json",
        },
        cookies={"csrf_token": csrf},
    )
    assert r.status_code == 200

