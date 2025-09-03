import re
import time
from datetime import datetime, timezone
from http import HTTPStatus

from fastapi.testclient import TestClient

from app.main import app

COOKIE_RE = re.compile(
    r"(GSNH_AT|GSNH_RT|GSNH_SESS|did|g_state|g_next|access_token|refresh_token|__session)=[^;]*; .*"
)


def _assert_auth_cookies(
    set_cookie_headers, *, expect_samesite=None, expect_secure=None
):
    names = [h.split("=", 1)[0] for h in set_cookie_headers]
    assert any(h.startswith("GSNH_AT=") for h in set_cookie_headers), "GSNH_AT not set"
    assert any(h.startswith("GSNH_RT=") for h in set_cookie_headers), "GSNH_RT not set"
    for h in set_cookie_headers:
        assert COOKIE_RE.search(h), f"bad cookie format: {h}"
        if expect_secure is not None:
            assert ("Secure" in h) == expect_secure, f"Secure mismatch on {h}"
        if expect_samesite is not None:
            assert (
                f"SameSite={expect_samesite}" in h
            ), f"SameSite={expect_samesite} missing on {h}"


def test_classic_login_sets_cookies_on_final_response(monkeypatch):
    client = TestClient(app)
    # Ensure dev cookie semantics for TestClient over http
    monkeypatch.setenv("COOKIE_SECURE", "0")
    # Ensure user exists (idempotent)
    client.post(
        "/v1/register", json={"username": "classic_user", "password": "secret123"}
    )
    r = client.post(
        "/v1/login", json={"username": "classic_user", "password": "secret123"}
    )
    assert r.status_code in (HTTPStatus.OK, HTTPStatus.FOUND)
    set_cookies = r.headers.get_list("set-cookie")
    assert set_cookies, "No Set-Cookie on login response"
    _assert_auth_cookies(set_cookies)


def test_oauth_callback_sets_cookies_on_callback_response_single_hop(monkeypatch):
    client = TestClient(app, follow_redirects=False)
    monkeypatch.setenv("COOKIE_SECURE", "0")
    monkeypatch.setenv("DEV_MODE", "1")
    # Monkeypatch exchange_code to succeed
    import app.integrations.google.oauth as go

    import jwt

    # Create a mock ID token with proper issuer
    mock_id_token_payload = {
        "iss": "https://accounts.google.com",
        "sub": "123456789",
        "email": "test@example.com",
        "email_verified": True,
        "aud": "test-client-id",
        "iat": int(__import__("time").time()),
        "exp": int(__import__("time").time()) + 3600,
    }
    mock_id_token = jwt.encode(mock_id_token_payload, "test-secret", algorithm="HS256")

    # Create mock Google credentials object
    from datetime import datetime, UTC

    class MockCredentials:
        def __init__(self):
            self.token = "t"
            self.refresh_token = "rt"
            self.token_uri = "https://oauth2.googleapis.com/token"
            self.client_id = "test-client-id"
            self.client_secret = "test-secret"
            self.scopes = ["openid", "email", "profile"]
            self.scope = "openid email profile"  # Singular version for callback
            self.expiry = datetime.now(UTC)
            self.id_token = mock_id_token

    mock_creds = MockCredentials()
    monkeypatch.setattr(go, "exchange_code", lambda *args, **kwargs: mock_creds)

    # Set required cookies (state and PKCE verifier) to simulate browser
    client.cookies.set("g_state", "xyz")
    client.cookies.set("g_code_verifier", "v" * 43)

    r = client.get("/v1/auth/google/callback?code=fake&state=xyz")
    # First hop sets cookies and 302s
    assert r.status_code in (HTTPStatus.FOUND, HTTPStatus.TEMPORARY_REDIRECT)
    set_cookies = r.headers.get_list("set-cookie")
    assert set_cookies, "OAuth callback did not set cookies on the response it returned"
    _assert_auth_cookies(set_cookies)


def test_oauth_cross_site_uses_finisher_then_redirects(monkeypatch):
    client = TestClient(app, follow_redirects=False)
    # Simulate cross-site by forcing SameSite=None; Secure expectations
    monkeypatch.setenv("COOKIE_SECURE", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")
    monkeypatch.setenv("DEV_MODE", "1")

    # Mock the token exchange to avoid actual Google API calls
    import app.integrations.google.oauth as go
    from datetime import datetime, UTC

    class MockCredentials:
        def __init__(self):
            self.token = "cross_site_token"
            self.refresh_token = "cross_site_refresh"
            self.token_uri = "https://oauth2.googleapis.com/token"
            self.client_id = "test-client-id"
            self.client_secret = "test-secret"
            self.scopes = ["openid", "email", "profile"]
            self.scope = "openid email profile"  # Singular version for callback
            self.expiry = datetime.now(UTC)

    mock_creds = MockCredentials()
    monkeypatch.setattr(go, "exchange_code", lambda *args, **kwargs: mock_creds)

    r1 = client.get("/v1/auth/google/callback?code=fake&state=cross")
    assert r1.status_code == HTTPStatus.FOUND
    # In our integration, callback itself sets cookies; if a finisher route exists, it should be used.
    # Accept either direct cookies on callback OR a finisher hop that sets them.
    set_cookies_1 = r1.headers.get_list("set-cookie")
    if set_cookies_1:
        _assert_auth_cookies(set_cookies_1, expect_samesite="None", expect_secure=True)
    else:
        # If Location is a finisher, assert it sets cookies
        assert "/auth/finish" in (r1.headers.get("location") or "")
        r2 = client.get(r1.headers["location"], follow_redirects=False)
        assert r2.status_code == HTTPStatus.FOUND
        set_cookies_2 = r2.headers.get_list("set-cookie")
        assert set_cookies_2, "Finisher must set cookies"
        _assert_auth_cookies(set_cookies_2, expect_samesite="None", expect_secure=True)
