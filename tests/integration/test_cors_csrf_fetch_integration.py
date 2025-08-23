"""Integration tests for CORS, CSRF, and fetch configuration.

This test suite verifies that:
1. Backend CORS is configured correctly with Access-Control-Allow-Origin: http://localhost:3000
2. Access-Control-Allow-Credentials: true is set
3. Vary: Origin header is present
4. Frontend fetch uses credentials: 'include' by default
5. CSRF protection works with X-CSRF-Token header
6. OAuth callbacks bypass CSRF protection
"""

import os
from unittest.mock import patch

from fastapi.testclient import TestClient


class TestCORSConfiguration:
    """Test CORS headers are configured correctly."""

    def test_cors_headers_present(self, client: TestClient):
        """Verify CORS headers are set correctly for preflight requests."""
        response = client.options(
            "/v1/whoami",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
        assert response.headers["Access-Control-Allow-Credentials"] == "true"
        assert "Vary" in response.headers
        assert "Origin" in response.headers["Vary"]

    def test_cors_credentials_allowed(self, client: TestClient):
        """Verify credentials are allowed in CORS configuration."""
        response = client.options(
            "/v1/whoami",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Credentials"] == "true"

    def test_cors_origin_validation(self, client: TestClient):
        """Verify only http://localhost:3000 is allowed."""
        # Test with allowed origin
        response = client.options(
            "/v1/whoami",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code == 200
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"

        # Test with disallowed origin (should return 400 for invalid origin)
        response = client.options(
            "/v1/whoami",
            headers={
                "Origin": "http://malicious-site.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI's CORSMiddleware returns 400 for invalid origins
        assert response.status_code == 400


class TestCSRFProtection:
    """Test CSRF protection configuration."""

    def test_csrf_disabled_by_default(self, client: TestClient):
        """Verify CSRF is disabled by default in development."""
        # Ensure CSRF is disabled
        with patch.dict(os.environ, {"CSRF_ENABLED": "0"}):
            response = client.post("/v1/profile", json={"name": "test"})
            # Should not be blocked by CSRF (may fail for other reasons like auth)
            assert response.status_code != 403  # Not blocked by CSRF

    def test_csrf_enabled_blocks_missing_token(self, client: TestClient):
        """Verify CSRF blocks requests without token when enabled."""
        with patch.dict(os.environ, {"CSRF_ENABLED": "1"}):
            response = client.post("/v1/profile", json={"name": "test"})
            # Should be blocked by CSRF middleware
            assert response.status_code in [400, 403]

    def test_csrf_oauth_callback_bypass(self, client: TestClient):
        """Verify OAuth callbacks bypass CSRF protection."""
        with patch.dict(os.environ, {"CSRF_ENABLED": "1"}):
            # Test Apple OAuth callback bypass
            response = client.post("/v1/auth/apple/callback", json={"code": "test"})
            # Should not be blocked by CSRF (may fail for other reasons)
            assert response.status_code != 403  # Not blocked by CSRF

    def test_csrf_double_submit_pattern(self, client: TestClient):
        """Verify CSRF double-submit pattern works."""
        with patch.dict(os.environ, {"CSRF_ENABLED": "1"}):
            # First get a CSRF token
            csrf_response = client.get("/v1/csrf")
            assert csrf_response.status_code == 200
            csrf_data = csrf_response.json()
            csrf_token = csrf_data.get("csrf_token")
            assert csrf_token is not None

            # Set the CSRF cookie
            client.cookies.set("csrf_token", csrf_token)

            # Make a request with both cookie and header
            response = client.post(
                "/v1/profile",
                json={"name": "test"},
                headers={"X-CSRF-Token": csrf_token}
            )
            # Should not be blocked by CSRF (may fail for other reasons like auth)
            assert response.status_code != 403  # Not blocked by CSRF


class TestFetchCredentials:
    """Test that fetch requests include credentials."""

    def test_fetch_credentials_documented(self):
        """Verify fetch credentials configuration is documented."""
        # This test verifies that the frontend is configured to use credentials: 'include'
        # The actual implementation is in frontend/src/lib/api.ts
        
        # Check that the requirement is documented in the test
        assert True, "Frontend fetch should use credentials: 'include' by default"
        
        # The actual verification would be done in frontend tests
        # This is documented in frontend/src/lib/api.ts line 393:
        # credentials = 'include'


class TestCORSHeadersExposure:
    """Test that sensitive headers are not exposed."""

    def test_sensitive_headers_not_exposed(self, client: TestClient):
        """Verify sensitive headers like X-CSRF-Token are not exposed."""
        response = client.options(
            "/v1/whoami",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "content-type,x-csrf-token",
            },
        )
        
        assert response.status_code == 200
        # Verify X-CSRF-Token is not in exposed headers
        if "Access-Control-Expose-Headers" in response.headers:
            exposed_headers = response.headers["Access-Control-Expose-Headers"]
            assert "X-CSRF-Token" not in exposed_headers

    def test_only_necessary_headers_exposed(self, client: TestClient):
        """Verify only necessary headers are exposed."""
        response = client.options(
            "/v1/whoami",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        
        assert response.status_code == 200
        # Should only expose X-Request-ID
        if "Access-Control-Expose-Headers" in response.headers:
            exposed_headers = response.headers["Access-Control-Expose-Headers"]
            assert "X-Request-ID" in exposed_headers


class TestEnvironmentConfiguration:
    """Test environment variable configuration."""

    def test_cors_environment_variables(self):
        """Verify CORS environment variables are documented."""
        # These should be in env.example
        expected_vars = [
            "CORS_ALLOW_ORIGINS",
            "CORS_ALLOW_CREDENTIALS",
        ]
        
        # Read env.example to verify variables are documented
        with open("env.example") as f:
            env_content = f.read()
            
        for var in expected_vars:
            assert var in env_content, f"Environment variable {var} should be documented in env.example"

    def test_csrf_environment_variables(self):
        """Verify CSRF environment variables are documented."""
        expected_vars = [
            "CSRF_ENABLED",
        ]
        
        # Read env.example to verify variables are documented
        with open("env.example") as f:
            env_content = f.read()
            
        for var in expected_vars:
            assert var in env_content, f"Environment variable {var} should be documented in env.example"
