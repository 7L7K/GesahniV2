"""Test locked contract behavior for auth endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app


class TestWhoamiLockedContract:
    """Test that /v1/whoami always returns 200 with clear boolean is_authenticated."""

    def test_whoami_always_returns_200(self, client: TestClient):
        """Test that /v1/whoami never returns 401 or redirects."""
        # Test without any authentication
        response = client.get("/v1/whoami")
        assert response.status_code == 200
        
        # Verify response structure
        data = response.json()
        assert "is_authenticated" in data
        assert isinstance(data["is_authenticated"], bool)
        assert "session_ready" in data
        assert "user" in data
        assert "source" in data
        assert "version" in data
        
        # Verify no caching headers
        assert "Cache-Control" in response.headers
        assert "no-cache" in response.headers["Cache-Control"]
        assert "no-store" in response.headers["Cache-Control"]
        assert "must-revalidate" in response.headers["Cache-Control"]
        assert "Pragma" in response.headers
        assert response.headers["Pragma"] == "no-cache"
        assert "Expires" in response.headers
        assert response.headers["Expires"] == "0"

    def test_whoami_with_invalid_token_returns_200(self, client: TestClient):
        """Test that /v1/whoami returns 200 even with invalid tokens."""
        # Test with invalid Authorization header
        response = client.get("/v1/whoami", headers={"Authorization": "Bearer invalid_token"})
        assert response.status_code == 200
        
        data = response.json()
        assert data["is_authenticated"] is False
        assert data["session_ready"] is False
        assert data["source"] == "missing"

    def test_whoami_with_expired_token_returns_200(self, client: TestClient):
        """Test that /v1/whoami returns 200 even with expired tokens."""
        # Test with expired token in cookie
        response = client.get("/v1/whoami", cookies={"access_token": "expired.token.here"})
        assert response.status_code == 200
        
        data = response.json()
        assert data["is_authenticated"] is False
        assert data["session_ready"] is False

    def test_whoami_with_valid_token_returns_200(self, client: TestClient):
        """Test that /v1/whoami returns 200 with valid authentication."""
        # Create a valid token
        import jwt
        import time
        
        payload = {
            "user_id": "test_user",
            "sub": "test_user",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600
        }
        token = jwt.encode(payload, "change-me", algorithm="HS256")
        
        response = client.get("/v1/whoami", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        
        data = response.json()
        assert data["is_authenticated"] is True
        assert data["session_ready"] is True
        assert data["source"] == "header"
        assert data["user"]["id"] == "test_user"


class TestAuthFinishLockedContract:
    """Test that /v1/auth/finish always returns 204 and is idempotent."""

    @patch("app.api.auth._require_user_or_dev")
    def test_auth_finish_always_returns_204(self, mock_require_user, client: TestClient):
        """Test that POST /v1/auth/finish always returns 204."""
        mock_require_user.return_value = "test_user"
        
        response = client.post("/v1/auth/finish")
        assert response.status_code == 204

    @patch("app.api.auth._require_user_or_dev")
    def test_auth_finish_idempotent_first_call(self, mock_require_user, client: TestClient):
        """Test that first call to /v1/auth/finish sets cookies."""
        mock_require_user.return_value = "test_user"
        
        response = client.post("/v1/auth/finish")
        assert response.status_code == 204
        
        # Verify cookies were set - use raw headers access
        set_cookie_headers = [h for h in response.headers.raw if h[0].lower() == b'set-cookie']
        access_cookie = any(b'access_token' in h[1] for h in set_cookie_headers)
        refresh_cookie = any(b'refresh_token' in h[1] for h in set_cookie_headers)
        assert access_cookie
        assert refresh_cookie

    @patch("app.api.auth._require_user_or_dev")
    def test_auth_finish_idempotent_second_call(self, mock_require_user, client: TestClient):
        """Test that second call to /v1/auth/finish returns 204 without setting new cookies."""
        mock_require_user.return_value = "test_user"
        
        # First call - should set cookies
        response1 = client.post("/v1/auth/finish")
        assert response1.status_code == 204
        
        # Extract cookies from first response
        cookies = {}
        for h in response1.headers.raw:
            if h[0].lower() == b'set-cookie':
                cookie_str = h[1].decode('utf-8')
                if 'access_token' in cookie_str:
                    # Parse the cookie value
                    import re
                    match = re.search(r'access_token=([^;]+)', cookie_str)
                    if match:
                        cookies["access_token"] = match.group(1)
        
        # Second call with existing cookies - should return 204 without setting new cookies
        response2 = client.post("/v1/auth/finish", cookies=cookies)
        assert response2.status_code == 204
        
        # Verify no new cookies were set (idempotent behavior)
        set_cookie_headers = [h for h in response2.headers.raw if h[0].lower() == b'set-cookie']
        assert len(set_cookie_headers) == 0

    @patch("app.api.auth._require_user_or_dev")
    def test_auth_finish_idempotent_with_invalid_existing_cookies(self, mock_require_user, client: TestClient):
        """Test that call with invalid existing cookies still sets new cookies."""
        mock_require_user.return_value = "test_user"
        
        # Call with invalid existing cookies
        response = client.post("/v1/auth/finish", cookies={"access_token": "invalid.token.here"})
        assert response.status_code == 204
        
        # Verify new cookies were set despite invalid existing ones
        set_cookie_headers = [h for h in response.headers.raw if h[0].lower() == b'set-cookie']
        access_cookie = any(b'access_token' in h[1] for h in set_cookie_headers)
        refresh_cookie = any(b'refresh_token' in h[1] for h in set_cookie_headers)
        assert access_cookie
        assert refresh_cookie

    @patch("app.api.auth._require_user_or_dev")
    def test_auth_finish_idempotent_with_different_user_cookies(self, mock_require_user, client: TestClient):
        """Test that call with cookies for different user still sets new cookies."""
        mock_require_user.return_value = "test_user"
        
        # Create token for different user
        import jwt
        import time
        
        payload = {
            "user_id": "different_user",
            "sub": "different_user",
            "iat": int(time.time()),
            "exp": int(time.time()) + 3600
        }
        token = jwt.encode(payload, "change-me", algorithm="HS256")
        
        # Call with cookies for different user
        response = client.post("/v1/auth/finish", cookies={"access_token": token})
        assert response.status_code == 204
        
        # Verify new cookies were set for current user
        set_cookie_headers = [h for h in response.headers.raw if h[0].lower() == b'set-cookie']
        access_cookie = any(b'access_token' in h[1] for h in set_cookie_headers)
        refresh_cookie = any(b'refresh_token' in h[1] for h in set_cookie_headers)
        assert access_cookie
        assert refresh_cookie

    @pytest.mark.skip(reason="GET route has dependency issues in test environment")
    @patch("app.api.auth._require_user_or_dev")
    def test_auth_finish_get_returns_302(self, mock_require_user, client: TestClient):
        """Test that GET /v1/auth/finish returns 302 redirect."""
        mock_require_user.return_value = "test_user"
        
        # Try both paths to see which one works
        response = client.get("/v1/auth/finish")
        if response.status_code == 404:
            # Try without the /v1 prefix
            response = client.get("/auth/finish")
        
        assert response.status_code == 302
        assert "Location" in response.headers


class TestAuthFinishErrorHandling:
    """Test error handling in auth/finish endpoint."""

    @patch("app.api.auth._require_user_or_dev")
    def test_auth_finish_with_csrf_enabled(self, mock_require_user, client: TestClient):
        """Test CSRF protection when enabled."""
        mock_require_user.return_value = "test_user"
        
        with patch.dict("os.environ", {"CSRF_ENABLED": "1"}):
            # Should fail without CSRF token
            response = client.post("/v1/auth/finish")
            assert response.status_code == 403  # CSRF error

    @patch("app.api.auth._require_user_or_dev")
    def test_auth_finish_with_cross_site_intent_required(self, mock_require_user, client: TestClient):
        """Test cross-site intent header requirement."""
        mock_require_user.return_value = "test_user"
        
        with patch.dict("os.environ", {"COOKIE_SAMESITE": "none"}):
            # Should fail without intent header
            response = client.post("/v1/auth/finish")
            assert response.status_code == 401  # Missing intent header
            
            # Should succeed with intent header
            response = client.post("/v1/auth/finish", headers={"X-Auth-Intent": "refresh"})
            assert response.status_code == 204
