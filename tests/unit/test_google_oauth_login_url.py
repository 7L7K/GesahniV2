import os
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


class TestGoogleOAuthLoginURL:
    """Test the Google OAuth login URL endpoint."""

    def test_google_login_url_success(self):
        """Test successful Google OAuth login URL generation."""
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "test-client-id",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/v1/google/auth/callback",
                "JWT_SECRET": "test-secret",
            },
        ):
            response = client.get("/v1/google/auth/login_url?next=/dashboard")

            assert response.status_code == 200
            data = response.json()
            assert "url" in data
            assert "client_id=test-client-id" in data["url"]
            assert (
                "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fv1%2Fgoogle%2Fauth%2Fcallback"
                in data["url"]
            )
            assert "state=" in data["url"]
            assert "scope=openid+email+profile" in data["url"]

            # Check that cookie is set
            assert "g_state" in response.cookies
            # The cookie value should be present
            assert response.cookies["g_state"] is not None

    def test_google_login_url_missing_env_vars(self):
        """Test error handling when required environment variables are missing."""
        with patch.dict(os.environ, {}, clear=True):
            response = client.get("/v1/google/auth/login_url")

            assert response.status_code == 503
            data = response.json()
            assert "detail" in data
            assert "Google OAuth not configured" in data["detail"]
            assert "GOOGLE_CLIENT_ID" in data["detail"]
            assert "GOOGLE_REDIRECT_URI" in data["detail"]

    def test_google_login_url_with_optional_params(self):
        """Test Google OAuth login URL with optional parameters."""
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "test-client-id",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/v1/google/auth/callback",
                "GOOGLE_HD": "example.com",
                "GOOGLE_LOGIN_HINT": "user@example.com",
                "JWT_SECRET": "test-secret",
            },
        ):
            response = client.get("/v1/google/auth/login_url")

            assert response.status_code == 200
            data = response.json()
            assert "hd=example.com" in data["url"]
            assert "login_hint=user%40example.com" in data["url"]

    def test_google_login_url_default_next_param(self):
        """Test that default next parameter is used when not provided."""
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "test-client-id",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/v1/google/auth/callback",
                "JWT_SECRET": "test-secret",
            },
        ):
            response = client.get("/v1/google/auth/login_url")

            assert response.status_code == 200
            data = response.json()
            assert "redirect_params=%2F" in data["url"]  # URL-encoded "/"

    def test_google_login_url_custom_next_param(self):
        """Test that custom next parameter is properly encoded."""
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "test-client-id",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/v1/google/auth/callback",
                "JWT_SECRET": "test-secret",
            },
        ):
            response = client.get("/v1/google/auth/login_url?next=/admin/settings")

            assert response.status_code == 200
            data = response.json()
            assert "redirect_params=%2Fadmin%2Fsettings" in data["url"]

    def test_google_login_url_state_signature(self):
        """Test that state parameter includes a signature."""
        with patch.dict(
            os.environ,
            {
                "GOOGLE_CLIENT_ID": "test-client-id",
                "GOOGLE_REDIRECT_URI": "http://localhost:8000/v1/google/auth/callback",
                "JWT_SECRET": "test-secret",
            },
        ):
            response = client.get("/v1/google/auth/login_url")

            assert response.status_code == 200
            data = response.json()

            # Extract state from URL
            import urllib.parse

            parsed = urllib.parse.urlparse(data["url"])
            query_params = urllib.parse.parse_qs(parsed.query)
            state = query_params["state"][0]

            # State should contain timestamp:random:signature format
            parts = state.split(":")
            assert len(parts) == 3
            assert parts[0].isdigit()  # timestamp
            assert len(parts[1]) > 0  # random token
            assert len(parts[2]) > 0  # signature
