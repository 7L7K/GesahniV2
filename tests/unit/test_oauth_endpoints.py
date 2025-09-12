import os
from fastapi.testclient import TestClient
from app.main import app


def test_google_oauth_endpoints_exist():
    """Test that Google OAuth endpoints are accessible at expected paths."""
    # Ensure CSRF is disabled for this test
    os.environ["CSRF_ENABLED"] = "0"

    client = TestClient(app)

    # Test that OAuth endpoints return proper responses (not 404)
    # Note: These may return errors due to missing config, but should not be 404

    # Test Google OAuth login URL endpoint
    response = client.get("/v1/auth/google/login_url")
    assert response.status_code != 404, f"Google OAuth login URL endpoint should exist, got {response.status_code}"

    # Test Google OAuth callback endpoint
    response = client.get("/v1/auth/google/callback")
    assert response.status_code != 404, f"Google OAuth callback endpoint should exist, got {response.status_code}"


def test_legacy_google_oauth_redirects():
    """Test that legacy Google OAuth paths redirect properly."""
    # Ensure CSRF is disabled for this test
    os.environ["CSRF_ENABLED"] = "0"

    client = TestClient(app)

    # Test legacy /google/login redirects to new path
    response = client.get("/google/login", allow_redirects=False)
    assert response.status_code == 308, f"Legacy /google/login should redirect (308), got {response.status_code}"
    assert "/v1/auth/google/login_url" in response.headers.get("location", "")

    # Test legacy /google/status redirects to new path
    response = client.get("/google/status", allow_redirects=False)
    assert response.status_code == 308, f"Legacy /google/status should redirect (308), got {response.status_code}"
    assert "/v1/auth/google/status" in response.headers.get("location", "")


def test_legacy_auth_redirects():
    """Test that legacy auth paths redirect properly."""
    # Ensure CSRF is disabled for this test
    os.environ["CSRF_ENABLED"] = "0"

    client = TestClient(app)

    # Test legacy /login redirects
    response = client.get("/login", allow_redirects=False)
    assert response.status_code == 308, f"Legacy /login should redirect (308), got {response.status_code}"
    assert "/v1/auth/login" in response.headers.get("location", "")

    # Test legacy /logout redirects
    response = client.get("/logout", allow_redirects=False)
    assert response.status_code == 308, f"Legacy /logout should redirect (308), got {response.status_code}"
    assert "/v1/auth/logout" in response.headers.get("location", "")

    # Test legacy /register redirects
    response = client.get("/register", allow_redirects=False)
    assert response.status_code == 308, f"Legacy /register should redirect (308), got {response.status_code}"
    assert "/v1/auth/register" in response.headers.get("location", "")

    # Test legacy /refresh redirects
    response = client.get("/refresh", allow_redirects=False)
    assert response.status_code == 308, f"Legacy /refresh should redirect (308), got {response.status_code}"
    assert "/v1/auth/refresh" in response.headers.get("location", "")
