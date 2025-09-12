"""
Tests for app/api/auth.py endpoints

Target coverage: 35-45% selective
- whoami, refresh, logout happy paths
- 2 error branches per endpoint
- FastAPI TestClient with dependency overrides for get_current_user_id
- End-to-end cookie behavior
"""

import time
from unittest.mock import patch

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.auth import router as auth_router
from app.deps.user import get_current_user_id


# Test helpers
def _mint_token(
    secret: str, user_id: str, token_type: str = "access", ttl_s: int = 300
) -> str:
    """Helper to mint JWT tokens for testing"""
    now = int(time.time())
    payload = {
        "user_id": user_id,
        "sub": user_id,
        "iat": now,
        "exp": now + ttl_s,
        "type": token_type,
    }
    if token_type == "refresh":
        payload["jti"] = "test-jti-123"

    return jwt.encode(payload, secret, algorithm="HS256")


def _create_test_app():
    """Create a test FastAPI app with auth router and database setup"""
    app = FastAPI()

    # Set up test database before including routers
    import os
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    # Create temp DB path
    test_db_path = tempfile.mktemp(suffix=".db")
    os.environ["CARE_DB"] = test_db_path
    os.environ["AUTH_DB"] = test_db_path
    os.environ["MUSIC_DB"] = test_db_path

    # Ensure parent directory exists
    Path(test_db_path).parent.mkdir(parents=True, exist_ok=True)

    # Set up database tables
    try:
        result = subprocess.run(
            [sys.executable, "test_setup_db.py"],
            capture_output=True,
            text=True,
            cwd=os.getcwd(),
        )
        if result.returncode != 0:
            print(f"DB setup failed: {result.stderr}")
    except Exception as e:
        print(f"DB setup failed: {e}")

    app.include_router(auth_router, prefix="/v1")
    return app


class TestWhoami:
    """Test /v1/whoami endpoint"""

    def test_whoami_valid_cookie_happy_path(self, monkeypatch):
        """Test whoami with valid access token in cookie - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Set valid access token cookie
        token = _mint_token(
            "test-secret-key-for-testing-only-not-for-production", "alice"
        )
        client.cookies.set("access_token", token)

        # Make request
        response = client.get("/v1/whoami")

        # Assert happy path response
        assert response.status_code == 200
        data = response.json()
        assert data["is_authenticated"] is True
        assert data["user"]["id"] == "alice"
        assert "email" in data["user"]  # May be None
        assert data["source"] == "cookie"
        assert data["version"] == 1

    def test_whoami_valid_header_happy_path(self, monkeypatch):
        """Test whoami with valid access token in Authorization header - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Set valid access token in header
        token = _mint_token(
            "test-secret-key-for-testing-only-not-for-production", "bob"
        )

        # Make request
        response = client.get(
            "/v1/whoami", headers={"Authorization": f"Bearer {token}"}
        )

        # Assert happy path response
        assert response.status_code == 200
        data = response.json()
        assert data["is_authenticated"] is True
        assert data["user"]["id"] == "bob"
        assert "email" in data["user"]  # May be None
        assert data["source"] == "header"
        assert data["version"] == 1

    def test_whoami_no_token_error(self, monkeypatch):
        """Test whoami with no tokens - returns 401 Unauthorized"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Make request without any tokens
        response = client.get("/v1/whoami")

        # Assert unauthenticated response
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Unauthorized"

    def test_whoami_expired_token_error(self, monkeypatch):
        """Test whoami with expired token - returns 401 Unauthorized"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Set expired token (expired by more than JWT leeway to ensure failure)
        expired_token = _mint_token(
            "test-secret-key-for-testing-only-not-for-production", "expired", ttl_s=-120
        )
        client.cookies.set("access_token", expired_token)

        # Make request
        response = client.get("/v1/whoami")

        # Assert unauthenticated response
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Unauthorized"


class TestRefresh:
    """Test /v1/auth/refresh endpoint"""

    def test_refresh_valid_token_happy_path(self, monkeypatch):
        """Test refresh with valid refresh token - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        monkeypatch.setenv("JWT_REFRESH_TTL_SECONDS", "3600")  # 1 hour

        app = _create_test_app()
        client = TestClient(app)

        # Create and set refresh token cookie
        refresh_token = _mint_token(
            "test-secret-key-for-testing-only-not-for-production", "alice", "refresh"
        )
        client.cookies.set("refresh_token", refresh_token)

        # Mock the rotate_refresh_cookies function to return success
        with patch("app.api.auth.rotate_refresh_cookies") as mock_rotate:
            mock_rotate.return_value = {
                "access_token": "new_access_token",
                "refresh_token": "new_refresh_token",
                "user_id": "alice",
            }

            # Make refresh request
            response = client.post("/v1/auth/refresh")

            # Assert happy path response
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["user_id"] == "alice"
            assert "access_token" in data
            assert "refresh_token" in data

    def test_refresh_no_token_error(self, monkeypatch):
        """Test refresh with no refresh token - error branch"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Make refresh request without token
        response = client.post("/v1/auth/refresh")

        # Assert error response
        assert response.status_code == 401
        assert "invalid_refresh" in response.json().get("detail", "")

    def test_refresh_invalid_token_error(self, monkeypatch):
        """Test refresh with invalid refresh token - error branch"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Set invalid refresh token
        client.cookies.set("refresh_token", "invalid_token")

        # Mock rotate_refresh_cookies to return None (failure)
        with patch("app.api.auth.rotate_refresh_cookies") as mock_rotate:
            mock_rotate.return_value = None

            # Make refresh request
            response = client.post("/v1/auth/refresh")

            # Assert error response
            assert response.status_code == 401
            assert "invalid_refresh" in response.json().get("detail", "")


class TestLogout:
    """Test /v1/auth/logout endpoint"""

    def test_logout_happy_path(self, monkeypatch):
        """Test logout - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Set some auth cookies
        client.cookies.set("access_token", "some_access_token")
        client.cookies.set("refresh_token", "some_refresh_token")
        client.cookies.set("session_id", "some_session_id")

        # Make logout request
        response = client.post("/v1/auth/logout")

        # Assert happy path response
        assert response.status_code == 204
        assert response.content == b""

        # Check that cookies are cleared (this would be implementation dependent)
        # The actual cookie clearing is tested in other integration tests

    def test_logout_no_cookies_still_works(self, monkeypatch):
        """Test logout when no cookies are present - still works"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Make logout request without any cookies
        response = client.post("/v1/auth/logout")

        # Should still return 204 even without cookies
        assert response.status_code == 204
        assert response.content == b""


class TestPats:
    """Test PAT-related endpoints"""

    def test_list_pats_happy_path(self, monkeypatch):
        """Test list_pats - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()

        # Override get_current_user_id dependency
        def mock_get_current_user_id():
            return "test-user-id"

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        client = TestClient(app)

        # Make request
        response = client.get("/v1/pats")

        # Assert happy path response
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)  # Currently returns empty list

    def test_create_pat_happy_path(self, monkeypatch):
        """Test create_pat - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()

        # Override get_current_user_id dependency
        def mock_get_current_user_id():
            return "test-user-id"

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        client = TestClient(app)

        # Mock the database functions to avoid foreign key issues
        with patch("app.api.auth._ensure_auth") as mock_ensure, patch(
            "app.api.auth._create_pat"
        ) as mock_create:

            mock_ensure.return_value = None
            mock_create.return_value = None

            # Make request with valid PAT data
            pat_data = {"name": "Test PAT", "scopes": ["admin:write"], "exp_at": None}
            response = client.post("/v1/pats", json=pat_data)

            # Assert happy path response
            assert response.status_code == 200
            data = response.json()
            assert "id" in data
            assert "token" in data
            assert data["scopes"] == ["admin:write"]

    def test_create_pat_unauthorized_error(self, monkeypatch):
        """Test create_pat with anonymous user - error branch"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()

        # Override get_current_user_id to return "anon"
        def mock_get_current_user_id():
            return "anon"

        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
        client = TestClient(app)

        # Make request
        pat_data = {"name": "Test PAT", "scopes": ["admin:write"], "exp_at": None}
        response = client.post("/v1/pats", json=pat_data)

        # Assert 401 error
        assert response.status_code == 401
        assert "Unauthorized" in response.json().get("detail", "")


class TestLogin:
    """Test /v1/auth/login endpoint"""

    def test_login_happy_path(self, monkeypatch):
        """Test login - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        monkeypatch.setenv("JWT_REFRESH_TTL_SECONDS", "3600")  # 1 hour

        app = _create_test_app()
        client = TestClient(app)

        # Make login request
        response = client.post("/v1/auth/login", params={"username": "testuser"})

        # Assert happy path response
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["user_id"] == "testuser"

        # Check that cookies are set
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    def test_login_missing_username_error(self, monkeypatch):
        """Test login with missing username - error branch"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Make login request without username
        response = client.post("/v1/auth/login", params={"username": ""})

        # Assert 400 error
        assert response.status_code == 400
        assert "missing_username" in response.json().get("detail", "")

    def test_login_rate_limit_error(self, monkeypatch):
        """Test login rate limiting - error branch"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Mock rate limiting to simulate too many requests
        with patch("app.token_store.incr_login_counter") as mock_incr:
            mock_incr.return_value = 50  # Above IP limit of 30

            # Make login request
            response = client.post("/v1/auth/login", params={"username": "testuser"})

            # Assert 429 error
            assert response.status_code == 429
            assert "too_many_requests" in response.json().get("detail", "")


class TestFinish:
    """Test /v1/auth/finish endpoint"""

    def test_finish_happy_path(self, monkeypatch):
        """Test finish with valid user - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        monkeypatch.setenv("JWT_REFRESH_TTL_SECONDS", "3600")

        app = _create_test_app()

        # Override _require_user_or_dev dependency
        def mock_require_user_or_dev():
            return "test-user-id"

        from app.api.auth import _require_user_or_dev

        app.dependency_overrides[_require_user_or_dev] = mock_require_user_or_dev

        client = TestClient(app)

        # Make finish request
        response = client.post("/v1/auth/finish")

        # Assert happy path response (204 for POST)
        assert response.status_code == 204
        assert response.content == b""

        # Check that cookies are set
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies

    def test_finish_get_redirect_happy_path(self, monkeypatch):
        """Test finish GET with redirect - happy path"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        monkeypatch.setenv("JWT_REFRESH_TTL_SECONDS", "3600")

        app = _create_test_app()

        # Override _require_user_or_dev dependency
        def mock_require_user_or_dev():
            return "test-user-id"

        from app.api.auth import _require_user_or_dev

        app.dependency_overrides[_require_user_or_dev] = mock_require_user_or_dev

        client = TestClient(
            app, follow_redirects=False
        )  # Don't follow redirects in test

        # Make finish GET request
        response = client.get("/v1/auth/finish?next=/dashboard")

        # Assert redirect response
        assert response.status_code == 302
        assert "Location" in response.headers
        location = response.headers["Location"]
        assert "/" in location  # Should redirect to next or default

        # Check that cookies are set
        assert "access_token" in response.cookies
        assert "refresh_token" in response.cookies


class TestWhoamiAdvanced:
    """Additional whoami test scenarios"""

    def test_whoami_priority_order(self, monkeypatch):
        """Test whoami priority order: cookie > header"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Set both cookie and header tokens
        cookie_token = _mint_token(
            "test-secret-key-for-testing-only-not-for-production", "cookie-user"
        )
        header_token = _mint_token(
            "test-secret-key-for-testing-only-not-for-production", "header-user"
        )

        client.cookies.set("access_token", cookie_token)

        # Make request with header token
        response = client.get(
            "/v1/whoami", headers={"Authorization": f"Bearer {header_token}"}
        )

        # Assert cookie takes priority over header
        assert response.status_code == 200
        data = response.json()
        assert data["is_authenticated"] is True
        assert data["user"]["id"] == "cookie-user"  # Cookie takes priority
        assert data["source"] == "cookie"
        assert data["version"] == 1

    def test_whoami_invalid_jwt_secret_error(self, monkeypatch):
        """Test whoami when JWT_SECRET is missing - returns 401 Unauthorized"""
        # Don't set JWT_SECRET
        app = _create_test_app()
        client = TestClient(app)

        # Set a token that would require JWT_SECRET
        client.cookies.set("access_token", "some-invalid-token")

        # Make request
        response = client.get("/v1/whoami")

        # Should return 401 Unauthorized
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Unauthorized"

    def test_whoami_malformed_token_error(self, monkeypatch):
        """Test whoami with malformed JWT token - returns 401 Unauthorized"""
        monkeypatch.setenv(
            "JWT_SECRET", "test-secret-key-for-testing-only-not-for-production"
        )
        app = _create_test_app()
        client = TestClient(app)

        # Set malformed token
        client.cookies.set("access_token", "malformed-token")

        # Make request
        response = client.get("/v1/whoami")

        # Assert 401 Unauthorized response
        assert response.status_code == 401
        data = response.json()
        assert data["detail"] == "Unauthorized"
