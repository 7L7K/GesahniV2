"""
Tests for app/api/google_oauth.py endpoints

Target coverage: 35-45% selective
- login_url: missing config (503), happy path with state cookies
- callback: bad state (400), token exchange fail (502/500), happy path with redirect
"""

import hashlib
import hmac
import secrets
import time
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.google_oauth import router as google_oauth_router


def _generate_test_state():
    """Generate a valid test state token"""
    timestamp = str(int(time.time()))
    random_token = secrets.token_urlsafe(16)  # Use same method as actual implementation
    message = f"{timestamp}:{random_token}".encode()

    # Use a test secret
    secret = "test_state_secret"
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:12]

    return f"{timestamp}:{random_token}:{signature}"


def _create_test_app():
    """Create a test FastAPI app with Google OAuth router"""
    app = FastAPI()
    app.include_router(google_oauth_router, prefix="/v1")
    return app


class TestGoogleLoginUrl:
    """Test /v1/google/auth/login_url endpoint"""

    def test_login_url_missing_config_error(self, monkeypatch):
        """Test login_url when Google OAuth not configured - 503 error"""
        # Clear Google OAuth config
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)

        app = _create_test_app()
        client = TestClient(app)

        # Make request
        response = client.get("/v1/google/auth/login_url")

        # Assert 503 error
        assert response.status_code == 503
        data = response.json()
        assert "Google OAuth not configured" in data["detail"]

    def test_login_url_happy_path(self, monkeypatch):
        """Test login_url with valid config - happy path with state cookie"""
        # Set up Google OAuth config
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        monkeypatch.setenv(
            "GOOGLE_REDIRECT_URI", "http://testserver/google/auth/callback"
        )
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Make request
        response = client.get("/v1/google/auth/login_url?next=/dashboard")

        # Assert happy path response
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data

        auth_url = data["auth_url"]
        assert "https://accounts.google.com/o/oauth2/v2/auth" in auth_url
        assert "client_id=test_client_id" in auth_url
        assert (
            "redirect_uri=http%3A%2F%2Ftestserver%2Fgoogle%2Fauth%2Fcallback"
            in auth_url
        )
        assert "response_type=code" in auth_url
        assert "scope=openid+email+profile" in auth_url

        # Check that state cookie is set
        assert "g_state" in response.cookies

    def test_login_url_with_optional_params(self, monkeypatch):
        """Test login_url with optional Google parameters"""
        # Set up config with optional parameters
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        monkeypatch.setenv(
            "GOOGLE_REDIRECT_URI", "http://testserver/google/auth/callback"
        )
        monkeypatch.setenv("GOOGLE_HD", "example.com")
        monkeypatch.setenv("GOOGLE_LOGIN_HINT", "user@example.com")
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Make request
        response = client.get("/v1/google/auth/login_url")
        data = response.json()
        auth_url = data["auth_url"]

        # Assert optional parameters are included
        assert "hd=example.com" in auth_url
        assert "login_hint=user%40example.com" in auth_url


class TestGoogleCallback:
    """Test /v1/google/auth/callback endpoint"""

    def test_callback_missing_code_error(self, monkeypatch):
        """Test callback with missing code parameter - 400 error"""
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Make request without code parameter
        response = client.get("/v1/google/auth/callback?state=test_state")

        # Assert 400 error
        assert response.status_code == 400
        data = response.json()
        assert "missing_code_or_state" in data["detail"]

    def test_callback_missing_state_error(self, monkeypatch):
        """Test callback with missing state parameter - 400 error"""
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Make request without state parameter
        response = client.get("/v1/google/auth/callback?code=test_code")

        # Assert 400 error
        assert response.status_code == 400
        data = response.json()
        assert "missing_code_or_state" in data["detail"]

    def test_callback_bad_state_error(self, monkeypatch):
        """Test callback with invalid state - 400 error"""
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Set invalid state cookie
        client.cookies.set("g_state", "invalid_state")

        # Make request with mismatched state
        response = client.get(
            "/v1/google/auth/callback?code=test_code&state=different_state"
        )

        # Assert 400 error
        assert response.status_code == 400
        data = response.json()
        assert "state_mismatch" in data["detail"]

    def test_callback_expired_state_error(self, monkeypatch):
        """Test callback with expired state - 400 error"""
        # Turn off dev mode to enforce state validation
        monkeypatch.setenv("DEV_MODE", "0")
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Generate an expired state (timestamp from 6 minutes ago)
        old_timestamp = str(int(time.time()) - 360)
        random_token = "test_random_123"
        message = f"{old_timestamp}:{random_token}".encode()
        secret = "test_state_secret"
        signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:12]
        expired_state = f"{old_timestamp}:{random_token}:{signature}"

        # Set expired state cookie
        client.cookies.set("g_state", expired_state)

        # Make request with expired state
        response = client.get(
            f"/v1/google/auth/callback?code=test_code&state={expired_state}"
        )

        # Assert 400 error
        assert response.status_code == 400
        data = response.json()
        assert "invalid_state" in data["detail"]

    @patch("app.integrations.google.oauth.exchange_code")
    @patch("app.integrations.google.oauth.creds_to_record")
    @patch("app.integrations.google.db.init_db")
    def test_callback_token_exchange_failure(
        self, mock_init_db, mock_creds_to_record, mock_exchange, monkeypatch
    ):
        """Test callback when token exchange fails - 500 error"""
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")
        monkeypatch.setenv("JWT_SECRET", "test_jwt_secret")
        monkeypatch.setenv("APP_URL", "http://app.example")

        # Mock exchange_code to raise an exception
        mock_exchange.side_effect = Exception("Token exchange failed")

        app = _create_test_app()
        client = TestClient(app)

        # Set valid state cookie
        valid_state = _generate_test_state()
        client.cookies.set("g_state", valid_state)

        # Make callback request
        response = client.get(
            f"/v1/google/auth/callback?code=test_code&state={valid_state}"
        )

        # Assert 500 error
        assert response.status_code == 500
        data = response.json()
        assert "oauth_callback_failed" in data["detail"]

    @patch("app.integrations.google.oauth.exchange_code")
    @patch("app.integrations.google.oauth.creds_to_record")
    @patch("app.integrations.google.db.init_db")
    def test_callback_happy_path(
        self, mock_init_db, mock_creds_to_record, mock_exchange, monkeypatch
    ):
        """Test callback with successful OAuth flow - happy path with redirect"""
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")
        monkeypatch.setenv("JWT_SECRET", "test_jwt_secret")
        monkeypatch.setenv("APP_URL", "http://app.example")

        # Mock successful token exchange
        mock_creds = MagicMock()
        mock_creds.id_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InRlc3RAdGVzdC5jb20iLCJzdWIiOiJ0ZXN0LXN1YiJ9.test"
        mock_exchange.return_value = mock_creds

        # Mock creds_to_record
        mock_creds_to_record.return_value = {
            "access_token": "at",
            "refresh_token": "rt",
        }

        # Mock database operations
        mock_init_db.return_value = None

        app = _create_test_app()
        client = TestClient(app)

        # Set valid state cookie
        valid_state = _generate_test_state()
        client.cookies.set("g_state", valid_state)

        # Make callback request
        response = client.get(
            f"/v1/google/auth/callback?code=test_code&state={valid_state}",
            follow_redirects=False,
        )

        # Assert redirect response
        assert response.status_code in (302, 307)
        assert "Location" in response.headers
        location = response.headers["Location"]
        assert location.startswith("http://app.example/")

        # Check that auth cookies are set (tokens are in cookies, not URL)
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies


class TestGoogleCallbackErrors:
    """Test /v1/google/auth/callback endpoint error scenarios"""

    def test_callback_missing_code_error(self, monkeypatch):
        """Test callback with missing code parameter - 400 error"""
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Make request without code parameter
        response = client.get("/v1/google/auth/callback?state=test_state")

        # Assert 400 error
        assert response.status_code == 400
        data = response.json()
        assert "missing_code_or_state" in data["detail"]

    def test_callback_bad_state_mismatch_error(self, monkeypatch):
        """Test callback with state mismatch - 400 error"""
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Set invalid state cookie
        client.cookies.set("g_state", "invalid_state_cookie")

        # Make request with mismatched state
        response = client.get(
            "/v1/google/auth/callback?code=test_code&state=different_state"
        )

        # Assert 400 error
        assert response.status_code == 400
        data = response.json()
        assert "state_mismatch" in data["detail"]

    def test_callback_missing_state_cookie_error(self, monkeypatch):
        """Test callback with missing state cookie - 400 error"""
        # Turn off dev mode to enforce state cookie validation
        monkeypatch.setenv("DEV_MODE", "0")
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Make request without state cookie
        response = client.get(
            "/v1/google/auth/callback?code=test_code&state=test_state"
        )

        # Assert 400 error
        assert response.status_code == 400
        data = response.json()
        assert "missing_state_cookie" in data["detail"]

    def test_callback_expired_state_error(self, monkeypatch):
        """Test callback with expired state - 400 error"""
        # Turn off dev mode to enforce state validation
        monkeypatch.setenv("DEV_MODE", "0")
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")

        app = _create_test_app()
        client = TestClient(app)

        # Generate an expired state (timestamp from 6 minutes ago)
        expired_timestamp = str(int(time.time()) - 360)
        random_token = secrets.token_urlsafe(16)
        message = f"{expired_timestamp}:{random_token}".encode()
        secret = "test_state_secret"
        signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:12]
        expired_state = f"{expired_timestamp}:{random_token}:{signature}"

        # Set expired state cookie
        client.cookies.set("g_state", expired_state)

        # Make request with expired state
        response = client.get(
            f"/v1/google/auth/callback?code=test_code&state={expired_state}"
        )

        # Assert 400 error
        assert response.status_code == 400
        data = response.json()
        assert "invalid_state" in data["detail"]


class TestGoogleRedirectValidation:
    """Test redirect URL validation in Google OAuth"""

    def test_login_url_invalid_redirect_blocked(self, monkeypatch):
        """Test login_url with disallowed redirect URL"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        monkeypatch.setenv(
            "GOOGLE_REDIRECT_URI", "http://testserver/google/auth/callback"
        )
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")
        monkeypatch.setenv("OAUTH_REDIRECT_ALLOWLIST", "example.com")

        app = _create_test_app()
        client = TestClient(app)

        # Make request with disallowed redirect
        response = client.get(
            "/v1/google/auth/login_url?next=https://malicious.com/redirect"
        )

        # Assert redirect is blocked and reset to safe default
        assert response.status_code == 200
        data = response.json()
        auth_url = data["auth_url"]
        # Should not contain the malicious redirect
        assert "malicious.com" not in auth_url

    def test_login_url_allowed_redirect_passthrough(self, monkeypatch):
        """Test login_url with allowed redirect URL"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        monkeypatch.setenv(
            "GOOGLE_REDIRECT_URI", "http://testserver/google/auth/callback"
        )
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")
        monkeypatch.setenv("OAUTH_REDIRECT_ALLOWLIST", "example.com")

        app = _create_test_app()
        client = TestClient(app)

        # Make request with allowed redirect
        response = client.get(
            "/v1/google/auth/login_url?next=https://app.example.com/dashboard"
        )

        # Assert redirect is allowed
        assert response.status_code == 200
        data = response.json()
        auth_url = data["auth_url"]
        assert "app.example.com" in auth_url

    def test_login_url_no_allowlist_allows_all(self, monkeypatch):
        """Test login_url without allowlist allows any redirect"""
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        monkeypatch.setenv(
            "GOOGLE_REDIRECT_URI", "http://testserver/google/auth/callback"
        )
        monkeypatch.setenv("JWT_STATE_SECRET", "test_state_secret")
        # Don't set OAUTH_REDIRECT_ALLOWLIST

        app = _create_test_app()
        client = TestClient(app)

        # Make request with any redirect
        response = client.get(
            "/v1/google/auth/login_url?next=https://any-domain.com/path"
        )

        # Should allow the redirect when no allowlist is configured
        assert response.status_code == 200
        data = response.json()
        auth_url = data["auth_url"]
        assert "any-domain.com" in auth_url


class TestGoogleConfiguration:
    """Test Google OAuth configuration handling"""

    def test_login_url_missing_client_id_error(self, monkeypatch):
        """Test login_url when GOOGLE_CLIENT_ID is missing - 503 error"""
        # Clear Google OAuth config
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.setenv(
            "GOOGLE_REDIRECT_URI", "http://testserver/google/auth/callback"
        )

        app = _create_test_app()
        client = TestClient(app)

        # Make request
        response = client.get("/v1/google/auth/login_url")

        # Assert 503 error
        assert response.status_code == 503
        data = response.json()
        assert "Google OAuth not configured" in data["detail"]

    def test_login_url_missing_redirect_uri_error(self, monkeypatch):
        """Test login_url when GOOGLE_REDIRECT_URI is missing - 503 error"""
        # Clear Google OAuth config
        monkeypatch.setenv("GOOGLE_CLIENT_ID", "test_client_id")
        monkeypatch.delenv("GOOGLE_REDIRECT_URI", raising=False)

        app = _create_test_app()
        client = TestClient(app)

        # Make request
        response = client.get("/v1/google/auth/login_url")

        # Assert 503 error
        assert response.status_code == 503
        data = response.json()
        assert "Google OAuth not configured" in data["detail"]
