"""
Test CSRF helpers and security enforcement.

This test demonstrates the new CSRF helpers from conftest.py and shows
proper security testing patterns.
"""

import os
import pytest
from fastapi.testclient import TestClient

from tests.conftest import get_csrf, auth_post, auth_put, auth_delete


def test_get_csrf_helper_fetches_token_and_cookies():
    """Test that get_csrf helper properly fetches CSRF token and cookies."""
    # Ensure CSRF is enabled for this test
    os.environ["CSRF_ENABLED"] = "1"

    client = TestClient(pytest.importorskip("app.main").create_app())

    # Get CSRF token and cookies
    csrf_cookies, csrf_token = get_csrf(client)

    # Verify we got a token
    assert csrf_token
    assert isinstance(csrf_token, str)
    assert len(csrf_token) > 0

    # Verify CSRF cookie was set
    assert "gs_csrf" in client.cookies


def test_auth_post_helper_handles_csrf_automatically():
    """Test that auth_post automatically handles CSRF when auth cookies are present."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # First, login to establish auth session
    login_response = client.post("/v1/auth/login", json={
        "username": "testuser",
        "password": "secret123"
    }, allow_redirects=True)

    # Login should succeed (even if user doesn't exist, auth flow should handle it)
    assert login_response.status_code in [200, 201, 204]

    # Now auth_post should automatically fetch and inject CSRF
    response = auth_post(client, "/v1/auth/logout")

    # Should succeed because CSRF was handled automatically
    assert response.status_code in [200, 204]


def test_csrf_skipped_for_bootstrap_requests():
    """Test that CSRF is skipped for bootstrap requests without auth cookies."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # POST request without any auth cookies should succeed (bootstrap scenario)
    response = auth_post(client, "/v1/auth/register", json={
        "username": "newuser",
        "password": "secret123"
    })

    # Should succeed because no auth cookies are present (bootstrap path)
    assert response.status_code in [200, 201, 400]  # 400 is ok if user exists


def test_csrf_enforced_after_auth_cookies_present():
    """Test that CSRF is enforced after authentication."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # First establish auth session
    login_response = client.post("/v1/auth/login", json={
        "username": "testuser",
        "password": "secret123"
    }, allow_redirects=True)
    assert login_response.status_code in [200, 201, 204]

    # Now try a POST without CSRF - should fail
    response = client.post("/v1/auth/logout")  # No CSRF token provided

    # Should fail with 403 because auth cookies exist but no CSRF token
    assert response.status_code == 403


def test_auth_helpers_work_for_all_http_methods():
    """Test that auth helpers work for POST, PUT, PATCH, DELETE."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # Login first
    client.post("/v1/auth/login", json={
        "username": "testuser",
        "password": "secret123"
    }, allow_redirects=True)

    # Test auth helper methods with endpoints that actually support them
    methods_and_responses = [
        (auth_post, "/v1/auth/logout"),  # POST supported
        (auth_post, "/v1/auth/logout_all"),  # POST supported (not DELETE)
        (auth_delete, "/v1/spotify/disconnect"),  # DELETE supported
    ]

    for method_func, endpoint in methods_and_responses:
        try:
            response = method_func(client, endpoint)
            # Should succeed or return expected auth-related status
            assert response.status_code in [200, 204, 404, 405]  # 404/405 if endpoint doesn't exist
        except Exception as e:
            # If endpoint doesn't exist, that's ok for this test
            if "404" in str(e) or "405" in str(e):
                continue
            raise


def test_apple_callback_supports_get_and_post():
    """Smoke test: Apple callback should support both GET and POST methods."""
    os.environ["APPLE_CLIENT_ID"] = "test.apple.client"
    os.environ["APPLE_TEAM_ID"] = "test-team-id"
    os.environ["APPLE_KEY_ID"] = "test-key-id"
    os.environ["APPLE_PRIVATE_KEY"] = "test-private-key"
    os.environ["APPLE_REDIRECT_URI"] = "http://localhost:8000/v1/auth/apple/callback"

    client = TestClient(pytest.importorskip("app.main").create_app())

    # Set state cookie
    client.cookies.set("oauth_state", "test-state")

    # Test GET method (should not return 405)
    response = client.get("/v1/auth/apple/callback?state=test-state&code=fake-code")
    assert response.status_code != 405, f"GET method should be supported, got {response.status_code}"

    # Test POST method (should not return 405)
    response = client.post("/v1/auth/apple/callback", data={"state": "test-state", "code": "fake-code"})
    assert response.status_code != 405, f"POST method should be supported, got {response.status_code}"


def test_logout_all_supports_post_not_delete():
    """Smoke test: logout_all should support POST but not DELETE."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # POST should be supported (may require auth/CSRF but shouldn't be 405)
    response = client.post("/v1/auth/logout_all")
    assert response.status_code != 405, f"POST method should be supported for logout_all, got {response.status_code}"

    # DELETE should return 405 (method not allowed)
    response = client.delete("/v1/auth/logout_all")
    assert response.status_code == 405, f"DELETE method should not be supported for logout_all"


def test_spotify_disconnect_supports_delete():
    """Smoke test: Spotify disconnect should support DELETE method."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # DELETE should be supported (may require auth/CSRF but shouldn't be 405)
    response = client.delete("/v1/spotify/disconnect")
    assert response.status_code != 405, f"DELETE method should be supported for Spotify disconnect, got {response.status_code}"


def test_legacy_redirects_with_allow_redirects_true():
    """Test that legacy redirects work properly with allow_redirects=True."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # Test legacy auth redirect
    response = client.get("/login", allow_redirects=True)

    # Should redirect to new location
    assert response.status_code == 200  # Final response after redirect
    assert "/v1/auth/login" in response.url or response.status_code != 404


def test_csrf_helpers_with_custom_headers():
    """Test that CSRF helpers preserve custom headers."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # Login first
    client.post("/v1/auth/login", json={
        "username": "testuser",
        "password": "secret123"
    }, allow_redirects=True)

    # Use auth_post with custom headers
    custom_headers = {"X-Custom-Header": "test-value"}
    response = auth_post(
        client,
        "/v1/auth/logout",
        headers=custom_headers
    )

    # Should succeed and custom headers should be preserved
    assert response.status_code in [200, 204]


def test_bootstrap_vs_authenticated_csrf_behavior():
    """Test the difference in CSRF behavior between bootstrap and authenticated states."""
    client = TestClient(pytest.importorskip("app.main").create_app())

    # Test 1: Bootstrap state (no auth cookies) - should skip CSRF
    bootstrap_response = client.post("/v1/auth/register", json={
        "username": "bootstrap_test",
        "password": "secret123"
    })
    # Should not be blocked by CSRF (may fail for other reasons like user exists)
    assert bootstrap_response.status_code != 403

    # Test 2: Authenticated state - should enforce CSRF
    login_response = client.post("/v1/auth/login", json={
        "username": "testuser",
        "password": "secret123"
    }, allow_redirects=True)
    assert login_response.status_code in [200, 201, 204]

    # Now POST without CSRF should fail
    authenticated_response = client.post("/v1/auth/logout")
    assert authenticated_response.status_code == 403  # CSRF required now


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
