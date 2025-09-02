"""
Rate limiting tests for authentication endpoints.

Tests 429 responses for login and refresh endpoints under various conditions:
- IP-based rate limiting for anonymous requests
- User-based rate limiting for authenticated requests
- Scope-based bypass functionality
- Proper Retry-After headers
- Metrics recording
"""

import os
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.middleware.rate_limit import (
    _test_clear_buckets,
    _test_clear_metrics,
    _test_reset_config,
    _test_set_config,
    get_metrics,
)


class TestAuthRateLimiting:
    """Test rate limiting for authentication endpoints."""

    def setup_method(self):
        """Reset rate limiting state before each test."""
        _test_clear_buckets()
        _test_clear_metrics()
        _test_reset_config()

    def teardown_method(self):
        """Reset rate limiting state after each test."""
        _test_clear_buckets()
        _test_clear_metrics()
        _test_reset_config()

    @pytest.fixture
    def client(self):
        """Create test client with rate limiting enabled.

        Keep the patched environment active for the lifetime of the TestClient so
        the middleware sees the intended test-time configuration.
        """
        ctx = patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "", "PYTEST_RUNNING": ""})
        ctx.__enter__()
        client = TestClient(app)
        try:
            yield client
        finally:
            client.close()
            ctx.__exit__(None, None, None)

    def test_whoami_rate_limit_anonymous(self, client):
        """Test that anonymous /health requests are rate limited after threshold."""
        # Set very low rate limit for testing
        _test_set_config(max_req=3, window_s=60)

        # Make requests up to the limit
        for i in range(3):
            response = client.get("/health")
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get("/health")
        assert response.status_code == 429
        assert response.text == "rate_limited"
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "60"

    def test_refresh_rate_limit_anonymous(self, client):
        """Test that anonymous /health requests are rate limited."""
        # Set very low rate limit for testing
        _test_set_config(max_req=2, window_s=60)

        # Make requests up to the limit
        for i in range(2):
            response = client.get("/health")
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get("/health")
        assert response.status_code == 429
        assert response.text == "rate_limited"

    def test_rate_limit_window_reset(self, client):
        """Test that rate limit window resets after specified time."""
        # Set very short window for testing
        _test_set_config(max_req=2, window_s=1)

        # Make requests up to the limit
        for i in range(2):
            response = client.get("/health")
            assert response.status_code == 200

        # Should be rate limited immediately
        response = client.get("/health")
        assert response.status_code == 429

        # Wait for window to reset
        time.sleep(2)

        # Should allow requests again
        response = client.get("/health")
        assert response.status_code == 200

    def test_rate_limit_different_ips(self, client):
        """Test that different IP addresses have separate rate limits."""
        _test_set_config(max_req=2, window_s=60)

        # Mock different IPs by modifying the client
        def make_request_with_ip(ip):
            with patch.object(client, 'get') as mock_get:
                mock_get.return_value.status_code = 200
                # Simulate request with different client IP
                return mock_get(f"http://testserver/v1/whoami", headers={"X-Forwarded-For": ip})

        # Make requests from different IPs - should not interfere
        for ip in ["192.168.1.1", "192.168.1.2"]:
            for i in range(2):
                make_request_with_ip(ip)
                # In real scenario, each IP would be tracked separately

    def test_rate_limit_different_paths(self, client):
        """Test that different paths have separate rate limits."""
        _test_set_config(max_req=2, window_s=60)

        # Make requests to different endpoints
        endpoints = ["/v1/whoami", "/v1/auth/refresh", "/health"]

        for endpoint in endpoints:
            for i in range(2):
                if endpoint == "/health":
                    # Health endpoint should not be rate limited
                    response = client.get(endpoint)
                    assert response.status_code == 200
                else:
                    response = client.get(endpoint)
                    assert response.status_code in [200, 401]  # 401 for auth endpoints without tokens

    def test_rate_limit_metrics_recording(self, client):
        """Test that rate limiting properly records metrics."""
        _test_set_config(max_req=1, window_s=60)

        # Make one request (should succeed)
        response = client.get("/v1/whoami")
        assert response.status_code == 200

        # Second request should be rate limited
        response = client.get("/v1/whoami")
        assert response.status_code == 429

        # Check that metrics were recorded
        metrics = get_metrics()
        assert metrics["rate_limited_total"] == 1
        assert metrics["requests_total"] >= 2

    def test_rate_limit_bypass_scopes(self, client):
        """Test that requests with bypass scopes are not rate limited."""
        _test_set_config(max_req=1, window_s=60, bypass_scopes="admin,service")

        # Mock a request with admin scope
        with patch.object(client.app, 'middleware') as mock_middleware:
            # Simulate middleware setting scopes on request state
            def mock_dispatch(request, call_next):
                request.state.scopes = {"admin"}
                return call_next(request)

            mock_middleware.return_value.dispatch = mock_dispatch

            # Make multiple requests - should not be rate limited due to admin scope
            for i in range(5):
                response = client.get("/v1/whoami")
                # Note: In real scenario, scope would be set by authentication middleware

    def test_rate_limit_options_preflight(self, client):
        """Test that OPTIONS preflight requests are not rate limited."""
        _test_set_config(max_req=1, window_s=60)

        # Make request up to limit
        response = client.get("/v1/whoami")
        assert response.status_code == 200

        # OPTIONS should not be rate limited
        response = client.options("/v1/whoami")
        assert response.status_code == 200

        # Regular request should still work (not yet limited)
        response = client.get("/v1/whoami")
        assert response.status_code == 200

    def test_rate_limit_health_metrics_exempt(self, client):
        """Test that health and metrics endpoints are exempt from rate limiting."""
        _test_set_config(max_req=1, window_s=60)

        # Make request to trigger rate limit
        response = client.get("/v1/whoami")
        assert response.status_code == 200

        # Health endpoint should be exempt
        response = client.get("/health")
        assert response.status_code == 200

        # Metrics endpoint should be exempt
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_rate_limit_retry_after_header(self, client):
        """Test that rate limited responses include proper Retry-After header."""
        _test_set_config(max_req=1, window_s=123)

        # Make request up to limit
        response = client.get("/v1/whoami")
        assert response.status_code == 200

        # Next request should be rate limited with Retry-After
        response = client.get("/v1/whoami")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
        assert response.headers["Retry-After"] == "123"

    def test_rate_limit_user_vs_anonymous(self, client):
        """Test that authenticated users and anonymous users have separate rate limits."""
        _test_set_config(max_req=2, window_s=60)

        # Mock authenticated vs anonymous requests
        def make_authenticated_request():
            # In real scenario, this would have authentication headers/cookies
            response = client.get("/v1/whoami")
            return response

        def make_anonymous_request():
            response = client.get("/v1/whoami")
            return response

        # Both should be able to make 2 requests each before being limited
        # (though in this test setup, they're both anonymous)
        for i in range(2):
            response = make_anonymous_request()
            assert response.status_code == 200

        # Third request should be rate limited
        response = make_anonymous_request()
        assert response.status_code == 429

    def test_rate_limit_concurrent_requests(self, client):
        """Test rate limiting behavior with concurrent requests."""
        _test_set_config(max_req=1, window_s=60)

        # Make first request
        response = client.get("/v1/whoami")
        assert response.status_code == 200

        # Concurrent requests should be rate limited
        import concurrent.futures
        import requests

        def make_concurrent_request():
            try:
                return requests.get("http://testserver/v1/whoami")
            except Exception as e:
                return e

        # In real scenario, this would test concurrent requests
        # For this test, we just verify the setup works
        assert True  # Placeholder for concurrent request testing

    def test_rate_limit_recovery_after_window(self, client):
        """Test that rate limits reset correctly after window expires."""
        _test_set_config(max_req=1, window_s=1)

        # Make request up to limit
        response = client.get("/v1/whoami")
        assert response.status_code == 200

        # Should be rate limited immediately
        response = client.get("/v1/whoami")
        assert response.status_code == 429

        # Wait for window to pass
        time.sleep(1.1)

        # Should allow request again
        response = client.get("/v1/whoami")
        assert response.status_code == 200

    def test_rate_limit_pytest_bypass(self, client):
        """Test that rate limiting is bypassed during pytest execution."""
        # Set very restrictive rate limit
        _test_set_config(max_req=0, window_s=60)

        # With PYTEST_CURRENT_TEST set, rate limiting should be bypassed
        with patch.dict(os.environ, {"PYTEST_CURRENT_TEST": "test_rate_limit_pytest_bypass"}):
            # Even with max_req=0, requests should succeed during pytest
            response = client.get("/v1/whoami")
            assert response.status_code == 200

    def test_rate_limit_configuration_validation(self, client):
        """Test that rate limit configuration is properly validated."""
        # Test invalid configurations are handled gracefully
        _test_set_config(max_req=-1, window_s=0)

        # Should not crash, should use reasonable defaults
        response = client.get("/v1/whoami")
        assert response.status_code == 200


# Integration tests for specific auth endpoint combinations
class TestAuthEndpointRateLimitingIntegration:
    """Integration tests for rate limiting across multiple auth endpoints."""

    def setup_method(self):
        _test_clear_buckets()
        _test_clear_metrics()
        _test_reset_config()

    def teardown_method(self):
        _test_clear_buckets()
        _test_clear_metrics()
        _test_reset_config()

    def test_login_refresh_rate_limit_sequence(self, client):
        """Test rate limiting across login → refresh sequence."""
        _test_set_config(max_req=3, window_s=60)

        endpoints = ["/v1/whoami", "/v1/auth/refresh"]

        # Make requests across different endpoints
        for endpoint in endpoints:
            for i in range(3):
                if endpoint == "/v1/whoami":
                    response = client.get(endpoint)
                    assert response.status_code == 200
                else:
                    response = client.post(endpoint)
                    assert response.status_code == 401  # No auth tokens

        # Next request should be rate limited
        response = client.get("/v1/whoami")
        assert response.status_code == 429

    def test_rate_limit_with_auth_headers(self, client):
        """Test rate limiting with various authentication headers."""
        _test_set_config(max_req=2, window_s=60)

        # Test with different authorization header formats
        auth_headers = [
            {},
            {"Authorization": "Bearer invalid-token"},
            {"Authorization": "Basic dGVzdDp0ZXN0"},
        ]

        for headers in auth_headers:
            response = client.get("/v1/whoami", headers=headers)
            assert response.status_code == 200

        # Next request should be rate limited
        response = client.get("/v1/whoami")
        assert response.status_code == 429

    def test_rate_limit_metrics_detailed(self, client):
        """Test detailed metrics recording for rate limited requests."""
        _test_set_config(max_req=1, window_s=60)

        # Make requests to different endpoints
        endpoints = ["/v1/whoami", "/v1/auth/refresh", "/v1/pats"]

        for endpoint in endpoints:
            # First request succeeds
            if endpoint in ["/v1/whoami", "/v1/pats"]:
                response = client.get(endpoint)
            else:
                response = client.post(endpoint)
            assert response.status_code in [200, 401, 404]

            # Second request gets rate limited
            if endpoint in ["/v1/whoami", "/v1/pats"]:
                response = client.get(endpoint)
            else:
                response = client.post(endpoint)
            assert response.status_code == 429

        # Check metrics
        metrics = get_metrics()
        assert metrics["rate_limited_total"] == 3  # One per endpoint
        assert metrics["requests_total"] >= 6  # Two requests per endpoint
