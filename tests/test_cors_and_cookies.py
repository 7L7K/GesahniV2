"""
CORS and Cookie Configuration Tests

Regression tests to ensure CORS headers and cookie flags are properly configured
for cross-origin authentication flows. These tests prevent Safari and other browsers
from blocking credentialed requests.
"""

import re
from typing import List

import pytest
from httpx import AsyncClient


def _has_flag(line: str, flag: str) -> bool:
    """Check if a cookie line contains a specific flag."""
    return re.search(fr"{flag}(;|$)", line, flags=re.IGNORECASE) is not None


def test_preflight_ok(app_client):
    """
    Test that OPTIONS preflight requests return proper CORS headers.

    This ensures browsers can make cross-origin requests with credentials.
    """
    response = app_client.options(
        "/v1/auth/whoami",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-csrf-token, content-type, x-auth-orchestrator",
        },
    )

    # Should return 200 or 204 (both acceptable for preflight)
    assert response.status_code in (200, 204), f"Preflight failed with {response.status_code}"

    # CORS headers must be present and correct
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"

    # Check that requested headers are allowed
    allow_headers = response.headers.get("access-control-allow-headers", "")
    assert "x-csrf-token" in allow_headers.lower()
    assert "content-type" in allow_headers.lower()
    assert "x-auth-orchestrator" in allow_headers.lower()


def test_login_sets_secure_none_cookies(app_client):
    """
    Test that login endpoint sets cookies with Safari-safe flags.

    Ensures cookies work across origins without being blocked by browsers.
    """
    response = app_client.post(
        "/v1/auth/login?username=tester",
        headers={
            "Origin": "http://localhost:3000",
            "Content-Type": "application/json",
        },
        json={"username": "tester", "password": "pw"},
    )

    # Login should succeed (200) or redirect (302)
    assert response.status_code in (200, 302), f"Login failed with {response.status_code}"

    # Get all Set-Cookie headers
    set_cookies: List[str] = response.headers.get_list("set-cookie")
    assert any("GSNH_AT=" in cookie for cookie in set_cookies), "Missing GSNH_AT cookie"

    # Verify all GSNH_ auth cookies have correct flags
    auth_cookies = [cookie for cookie in set_cookies if "GSNH_" in cookie]

    for cookie in auth_cookies:
        # Safari-critical flags
        assert _has_flag(cookie, "HttpOnly"), f"Cookie missing HttpOnly: {cookie}"
        assert _has_flag(cookie, "Secure"), f"Cookie missing Secure: {cookie}"
        assert _has_flag(cookie, "SameSite=None"), f"Cookie missing SameSite=None: {cookie}"

        # Host-only (no Domain attribute for Safari compatibility)
        assert "Domain=" not in cookie, f"Cookie should be host-only, found Domain=: {cookie}"

        # Correct path
        assert "Path=/;" in cookie or cookie.endswith("Path=/"), f"Cookie missing Path=/ : {cookie}"


def test_whoami_cors_headers(app_client):
    """
    Test that whoami endpoint returns proper CORS headers for both authenticated
    and unauthenticated requests.
    """
    # Test unauthenticated request
    response = app_client.get(
        "/v1/auth/whoami",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"

    # Verify response contains authentication state
    data = response.json()
    assert "is_authenticated" in data
    assert data["is_authenticated"] is False


def test_refresh_endpoints_cors(app_client):
    """
    Test that refresh endpoints return proper CORS headers.
    """
    # Test refresh-info endpoint
    response = app_client.get(
        "/v1/auth/refresh-info",
        headers={"Origin": "http://localhost:3000"},
    )

    # Should work even without authentication (returns false for refresh present/valid)
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_origin_specificity(app_client):
    """
    Test that CORS allows specific origins, not wildcard (*).

    This ensures security while allowing cross-origin auth.
    """
    # Test with allowed origin
    response = app_client.options(
        "/v1/auth/whoami",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code in (200, 204)
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    # Test with disallowed origin (if configured to restrict origins)
    # Note: This test assumes your CORS is configured to allow localhost:3000
    # If you want to test rejection, use an origin not in your allowlist
    response2 = app_client.options(
        "/v1/auth/whoami",
        headers={"Origin": "http://evil-site.com"},
    )

    # This should either reject the origin or allow it based on your CORS config
    # The important thing is that it's not returning "*" wildcard
    cors_origin = response2.headers.get("access-control-allow-origin")
    if cors_origin:
        assert cors_origin != "*", "CORS should not return wildcard origin (*)"
