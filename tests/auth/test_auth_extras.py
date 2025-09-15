import os
import sys
import tempfile
from importlib import import_module

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from jose import jwt


def _make_auth_app(monkeypatch, extra_env: dict | None = None):
    fd, db_path = tempfile.mkstemp()
    os.close(fd)
    monkeypatch.setenv("USERS_DB", db_path)
    monkeypatch.setenv("JWT_SECRET", "secret")
    # Use long TTL for testing to prevent expiry mid-test
    monkeypatch.setenv("PYTEST_RUNNING", "1")
    if extra_env:
        for k, v in extra_env.items():
            monkeypatch.setenv(k, str(v))
    # ensure a fresh module read of env constants
    sys.modules.pop("app.auth", None)
    auth = import_module("app.auth")
    from app.api.auth import router as auth_api_router

    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(auth_api_router, prefix="/v1")
    client = TestClient(app)
    return auth, client


def test_register_invalid_username(monkeypatch):
    _auth, client = _make_auth_app(monkeypatch)
    # too short
    r = client.post("/register", json={"username": "ab", "password": "secret1"})
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_username"
    # invalid chars
    r = client.post("/register", json={"username": "bad$", "password": "secret1"})
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_username"


def test_register_duplicate_username(monkeypatch):
    _auth, client = _make_auth_app(monkeypatch)
    r1 = client.post(
        "/register", json={"username": "test_user_123", "password": "test_password_123"}
    )
    assert r1.status_code == 200
    r2 = client.post(
        "/register", json={"username": "test_user_123", "password": "test_password_123"}
    )
    assert r2.status_code == 400
    assert r2.json()["detail"] == "username_taken"


def test_password_strength_policy(monkeypatch):
    # Enable strong policy; fallback heuristics apply when zxcvbn missing
    _auth, client = _make_auth_app(monkeypatch, {"PASSWORD_STRENGTH": "1"})
    # weak: only letters
    r = client.post(
        "/register", json={"username": "charlie", "password": "onlyletters"}
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "weak_password"
    # strong enough: alnum mix and >= 8
    r = client.post("/register", json={"username": "charlie2", "password": "abcd1234"})
    assert r.status_code == 200


def test_login_throttling_lockout(monkeypatch):
    env = {
        "LOGIN_ATTEMPT_WINDOW_SECONDS": 5,
        "LOGIN_ATTEMPT_MAX": 2,
        "LOGIN_LOCKOUT_SECONDS": 10,
    }
    _auth, client = _make_auth_app(monkeypatch, env)
    # create user
    client.post("/register", json={"username": "bob", "password": "abcd1234"})
    # two bad attempts
    for _ in range(2):
        r = client.post("/v1/auth/login", json={"username": "bob", "password": "wrong"})
        assert r.status_code == 401
    # third attempt should be rate limited
    r = client.post("/v1/auth/login", json={"username": "bob", "password": "wrong"})
    assert r.status_code == 429
    detail = r.json().get("detail")
    assert isinstance(detail, dict) and detail.get("error") == "rate_limited"
    assert isinstance(detail.get("retry_after"), int)


def test_refresh_with_access_token_rejected(monkeypatch):
    _auth, client = _make_auth_app(monkeypatch)
    client.post("/register", json={"username": "dana", "password": "abcd1234"})

    # supply a request state user_id via dependency override
    def fake_user_id(request: Request):
        request.state.user_id = "u"
        return "u"

    from app.deps.user import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = fake_user_id

    login = client.post(
        "/login", json={"username": "dana", "password": "abcd1234"}
    ).json()
    access = login["access_token"]
    r = client.post("/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 400
    assert r.json()["detail"] == "Invalid token type"


def test_refresh_issuer_mismatch(monkeypatch):
    _auth, client = _make_auth_app(monkeypatch, {"JWT_ISS": "good"})
    client.post("/register", json={"username": "erin", "password": "abcd1234"})

    def fake_user_id(request: Request):
        request.state.user_id = "u"
        return "u"

    from app.deps.user import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = fake_user_id

    login = client.post(
        "/login", json={"username": "erin", "password": "abcd1234"}
    ).json()
    # Craft a refresh token with wrong issuer
    payload = jwt.get_unverified_claims(login["refresh_token"])
    payload["iss"] = "bad"
    # Use jwt.encode directly for this test since we need to preserve the modified issuer
    bad_refresh = jwt.encode(payload, "secret", algorithm="HS256")
    r = client.post("/v1/auth/refresh", json={"refresh_token": bad_refresh})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid token issuer"


def test_forgot_and_reset_password_flow(monkeypatch):
    _auth, client = _make_auth_app(monkeypatch)
    client.post("/register", json={"username": "sam", "password": "abcd1234"})
    # Request reset token (returned in tests)
    r = client.post("/forgot", json={"username": "sam"})
    assert r.status_code == 200
    tok = r.json().get("token")
    assert tok

    # Weak new password rejected
    r = client.post("/reset_password", json={"token": tok, "new_password": "short"})
    assert r.status_code == 400
    assert r.json()["detail"] == "weak_password"

    # Use a valid new password
    r = client.post("/reset_password", json={"token": tok, "new_password": "newpass"})
    assert r.status_code == 200

    # Token cannot be reused
    r = client.post("/reset_password", json={"token": tok, "new_password": "another1"})
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_token"

    # Login with the new password should succeed
    def fake_user_id(request: Request):
        request.state.user_id = "u"
        return "u"

    from app.deps.user import get_current_user_id

    client.app.dependency_overrides[get_current_user_id] = fake_user_id

    r = client.post("/v1/auth/login", json={"username": "sam", "password": "newpass"})
    assert r.status_code == 200
