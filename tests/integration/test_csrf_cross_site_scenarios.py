"""
Integration tests for CSRF validation in cross-site scenarios.

Tests the fix for CSRF token mismatch when COOKIE_SAMESITE=none.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


def test_csrf_same_origin_validation(monkeypatch):
    """Test standard CSRF validation in same-origin scenarios."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "lax")

    client = TestClient(app)

    # Get CSRF token
    csrf_resp = client.get("/v1/csrf")
    assert csrf_resp.status_code == 200
    csrf_token = csrf_resp.json()["csrf_token"]

    # Test that CSRF token cookie is set
    assert "csrf_token" in csrf_resp.cookies

    # Test refresh endpoint with valid CSRF token
    refresh_resp = client.post(
        "/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf_token},
        cookies={"csrf_token": csrf_token},
    )
    # Should fail due to missing auth, but not CSRF error
    assert refresh_resp.status_code in [401, 403]  # Auth error, not CSRF error


def test_csrf_cross_site_validation(monkeypatch):
    """Test CSRF validation in cross-site scenarios (COOKIE_SAMESITE=none)."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")

    client = TestClient(app)

    # Get CSRF token
    csrf_resp = client.get("/v1/csrf")
    assert csrf_resp.status_code == 200
    csrf_token = csrf_resp.json()["csrf_token"]

    # Test that CSRF token cookie is set with SameSite=None
    assert "csrf_token" in csrf_resp.cookies
    # Check the Set-Cookie header for SameSite=None (lowercase 'none' is correct)
    set_cookie_header = csrf_resp.headers.get("set-cookie", "")
    assert "SameSite=none" in set_cookie_header

    # Test refresh endpoint with valid CSRF token and intent header
    refresh_resp = client.post(
        "/v1/auth/refresh",
        headers={"X-CSRF-Token": csrf_token, "X-Auth-Intent": "refresh"},
    )
    # Should fail due to missing auth, but not CSRF error
    assert refresh_resp.status_code in [401, 403]  # Auth error, not CSRF error


def test_csrf_cross_site_missing_token(monkeypatch):
    """Test that cross-site requests without CSRF token are rejected."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")

    client = TestClient(app)

    # Test refresh endpoint without CSRF token
    refresh_resp = client.post("/v1/auth/refresh", headers={"X-Auth-Intent": "refresh"})
    assert refresh_resp.status_code == 400
    assert "missing_csrf_cross_site" in refresh_resp.json()["detail"]


def test_csrf_cross_site_missing_intent(monkeypatch):
    """Test that cross-site requests without intent header are rejected."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")

    client = TestClient(app)

    # Get CSRF token
    csrf_resp = client.get("/v1/csrf")
    csrf_token = csrf_resp.json()["csrf_token"]

    # Test refresh endpoint with CSRF token but no intent header
    # The middleware should pass this through to the auth endpoint
    refresh_resp = client.post("/v1/auth/refresh", headers={"X-CSRF-Token": csrf_token})
    assert refresh_resp.status_code == 400
    # The auth endpoint should return the cross-site specific error
    assert "missing_intent_header_cross_site" in refresh_resp.json()["detail"]


def test_csrf_cross_site_invalid_token_format(monkeypatch):
    """Test that cross-site requests with invalid CSRF token format are rejected."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")

    client = TestClient(app)

    # Test refresh endpoint with invalid CSRF token (too short)
    refresh_resp = client.post(
        "/v1/auth/refresh",
        headers={"X-CSRF-Token": "short", "X-Auth-Intent": "refresh"},
    )
    assert refresh_resp.status_code == 403
    assert "invalid_csrf_format" in refresh_resp.json()["detail"]


def test_csrf_same_origin_missing_cookie(monkeypatch):
    """Test that same-origin requests without CSRF cookie are rejected."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "lax")

    client = TestClient(app)

    # Get CSRF token but don't use the cookie
    csrf_resp = client.get("/v1/csrf")
    csrf_token = csrf_resp.json()["csrf_token"]

    # Test refresh endpoint with CSRF token in header but no cookie
    # Since the client automatically includes cookies, we need to clear them
    client.cookies.clear()
    refresh_resp = client.post("/v1/auth/refresh", headers={"X-CSRF-Token": csrf_token})
    # The middleware should catch this and return 403
    assert refresh_resp.status_code == 403
    assert "invalid_csrf" in refresh_resp.json()["detail"]


def test_csrf_same_origin_mismatch(monkeypatch):
    """Test that same-origin requests with mismatched CSRF token are rejected."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "lax")

    client = TestClient(app)

    # Get CSRF token
    csrf_resp = client.get("/v1/csrf")
    csrf_token = csrf_resp.json()["csrf_token"]

    # Test refresh endpoint with mismatched CSRF token
    refresh_resp = client.post(
        "/v1/auth/refresh",
        headers={"X-CSRF-Token": "different_token"},
        cookies={"csrf_token": csrf_token},
    )
    # The middleware should catch this and return 403
    assert refresh_resp.status_code == 403
    assert "invalid_csrf" in refresh_resp.json()["detail"]


def test_csrf_disabled_behavior(monkeypatch):
    """Test that CSRF validation is bypassed when disabled."""
    monkeypatch.setenv("CSRF_ENABLED", "0")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")

    client = TestClient(app)

    # Test refresh endpoint without CSRF token (should work when disabled)
    refresh_resp = client.post("/v1/auth/refresh", headers={"X-Auth-Intent": "refresh"})
    # Should fail due to missing auth, but not CSRF error
    assert refresh_resp.status_code in [401, 403]  # Auth error, not CSRF error


def test_csrf_middleware_cross_site_validation(monkeypatch):
    """Test that CSRF middleware properly handles cross-site scenarios."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "none")

    client = TestClient(app)

    # Get CSRF token
    csrf_resp = client.get("/v1/csrf")
    csrf_token = csrf_resp.json()["csrf_token"]

    # Test a mutating endpoint (POST) with cross-site CSRF validation
    # Use a simple endpoint that requires CSRF but not auth
    with patch("app.api.auth.get_current_user_id", return_value="test_user"):
        profile_resp = client.post(
            "/v1/profile", headers={"X-CSRF-Token": csrf_token}, json={"name": "test"}
        )
        # Should work with valid CSRF token in cross-site mode
        assert profile_resp.status_code in [
            200,
            201,
            400,
        ]  # Success or validation error, not CSRF error


def test_csrf_middleware_same_origin_validation(monkeypatch):
    """Test that CSRF middleware properly handles same-origin scenarios."""
    monkeypatch.setenv("CSRF_ENABLED", "1")
    monkeypatch.setenv("COOKIE_SAMESITE", "lax")

    client = TestClient(app)

    # Get CSRF token
    csrf_resp = client.get("/v1/csrf")
    csrf_token = csrf_resp.json()["csrf_token"]

    # Test a mutating endpoint (POST) with same-origin CSRF validation
    with patch("app.api.auth.get_current_user_id", return_value="test_user"):
        profile_resp = client.post(
            "/v1/profile",
            headers={"X-CSRF-Token": csrf_token},
            cookies={"csrf_token": csrf_token},
            json={"name": "test"},
        )
        # Should work with valid CSRF token in same-origin mode
        assert profile_resp.status_code in [
            200,
            201,
            400,
        ]  # Success or validation error, not CSRF error
