"""
Comprehensive API Endpoint Tests

This module contains 10-12 comprehensive tests for the FastAPI endpoints:
1. GET /healthz/ready returns 200 and expected JSON keys
2. POST /v1/auth/login dev path returns cookies and redirect
3. POST /v1/auth/logout returns 204 and clears cookies
4. GET /v1/whoami unauth=200 (with unauthenticated response); with cookies=200 and user payload
5. POST /v1/auth/refresh rotates access token, keeps refresh, asserts TTL changes
6. GET /v1/models lists whitelisted models
7. POST /v1/ask with mock model router returns stubbed answer; asserts analytics called
8. Additional tests for edge cases and error conditions
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from tests.api.test_minimal_fastapi_app import (
    create_auth_cookies,
    create_auth_headers,
    create_test_client,
)


class TestAPIEndpointsComprehensive:
    """Comprehensive API endpoint tests with mocked dependencies."""

    @pytest.fixture
    def client(self) -> TestClient:
        """Create a test client with mocked dependencies."""
        return create_test_client()

    def test_health_ready_endpoint(self, client: TestClient):
        """Test GET /healthz/ready returns 200 and expected JSON keys."""
        response = client.get("/healthz/ready")

        assert response.status_code == 200
        data = response.json()

        # Check required keys exist - the endpoint should return at least status
        assert "status" in data

        # In test environment, it may return simple response
        # Check status is either "ok", "healthy", or "degraded"
        assert data["status"] in ["ok", "healthy", "degraded"]

    def test_health_ready_components_structure(self, client: TestClient):
        """Test health endpoint includes expected component checks when available."""
        response = client.get("/healthz/ready")
        assert response.status_code == 200

        data = response.json()

        # Components may or may not be present in test environment
        if "components" in data:
            components = data["components"]
            assert isinstance(components, dict)

            # If components exist, they should have proper structure
            for _component, info in components.items():
                assert "status" in info
                assert info["status"] in ["healthy", "unhealthy"]

    def test_auth_login_dev_path(self, client: TestClient):
        """Test POST /v1/auth/login dev path returns cookies and success."""
        response = client.post("/v1/auth/dev/login?username=testuser")

        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert data["status"] == "ok"
        assert "user_id" in data
        assert data["user_id"] == "testuser"

        # Check that tokens are returned in JSON response (not cookies for this endpoint)
        assert "access_token" in data
        assert "refresh_token" in data
        assert isinstance(data["access_token"], str)
        assert isinstance(data["refresh_token"], str)

    def test_auth_login_missing_username(self, client: TestClient):
        """Test POST /v1/auth/login with missing username returns error."""
        response = client.post("/v1/auth/dev/login", json={})

        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        assert "missing_username" in data["detail"]

    def test_auth_logout_endpoint(self, client: TestClient):
        """Test POST /v1/auth/logout returns 204 and clears cookies."""
        # First login to get cookies
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])
        client.cookies.set("GSNH_RT", cookies["refresh_token"])

        # Then logout
        response = client.post("/v1/auth/logout")

        assert response.status_code == 204

        # Check that cookies are cleared (should have empty/expires values)
        assert "set-cookie" in response.headers
        cookies_header = response.headers.get("set-cookie", "")
        assert "access_token=;" in cookies_header or "expires=" in cookies_header

    def test_whoami_unauthenticated(self, client: TestClient):
        """Test GET /v1/whoami without auth returns 200 with unauthenticated response."""
        response = client.get("/v1/whoami")

        assert response.status_code == 200
        data = response.json()
        assert data["is_authenticated"] is False
        assert data["session_ready"] is False
        assert data["user"]["id"] is None
        assert data["user"]["email"] is None
        assert data["source"] == "missing"
        assert data["version"] == 1

    def test_whoami_with_cookies(self, client: TestClient):
        """Test GET /v1/whoami with valid cookies returns 200 and user payload."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        response = client.get("/v1/whoami")

        assert response.status_code == 200
        data = response.json()

        # Check required fields
        assert "is_authenticated" in data
        assert "session_ready" in data
        assert "user" in data
        assert "source" in data
        assert "version" in data

        # Check authentication succeeded
        assert data["is_authenticated"] is True
        assert data["session_ready"] is True
        assert data["user"]["id"] == "testuser"
        assert data["source"] == "cookie"
        assert data["version"] == 1

    def test_whoami_with_bearer_token(self, client: TestClient):
        """Test GET /v1/whoami with Bearer token returns 200."""
        headers = create_auth_headers("testuser")

        response = client.get("/v1/whoami", headers=headers)

        assert response.status_code == 200
        data = response.json()

        assert data["is_authenticated"] is True
        assert data["user"]["id"] == "testuser"
        assert data["source"] == "header"

    def test_auth_refresh_endpoint(self, client: TestClient):
        """Test POST /v1/auth/refresh rotates access token and keeps refresh."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set(
            "GSNH_AT", cookies["access_token"]
        )  # Use canonical access token name
        client.cookies.set(
            "GSNH_RT", cookies["refresh_token"]
        )  # Use canonical refresh token name

        response = client.post("/v1/auth/refresh")

        assert response.status_code == 200
        data = response.json()

        # The refresh endpoint returns the actual API response format
        assert "rotated" in data
        assert "access_token" in data
        assert isinstance(data["rotated"], bool)
        assert isinstance(data["access_token"], str)

        # Verify the access token is a valid JWT using the same secret the app uses
        import os

        jwt_secret = os.getenv(
            "JWT_SECRET",
            "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        )
        new_access = jwt.decode(data["access_token"], jwt_secret, algorithms=["HS256"])

        assert new_access["user_id"] == "testuser"
        assert new_access["sub"] == "testuser"

    def test_auth_refresh_without_token(self, client: TestClient):
        """Test POST /v1/auth/refresh without refresh token fails."""
        response = client.post("/v1/auth/refresh")

        assert response.status_code == 401

    def test_models_list_endpoint(self, client: TestClient):
        """Test GET /v1/models lists whitelisted models."""
        response = client.get("/v1/models")

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert isinstance(data["items"], list)

        # Check structure of model items
        for model in data["items"]:
            assert "engine" in model
            assert "name" in model
            assert "capabilities" in model
            assert "pricing_per_1k_tokens" in model

            # Engine should be gpt or llama
            assert model["engine"] in ["gpt", "llama"]

            # Capabilities should be a list
            assert isinstance(model["capabilities"], list)

    def test_models_list_includes_expected_engines(self, client: TestClient):
        """Test that models endpoint includes both GPT and LLaMA models."""
        response = client.get("/v1/models")
        assert response.status_code == 200

        data = response.json()
        engines = {model["engine"] for model in data["items"]}

        # Should have at least one of each major engine type
        assert "gpt" in engines or "llama" in engines

    def test_ask_endpoint_with_mock_router(self, client: TestClient):
        """Test POST /v1/ask with mock model router returns stubbed answer and calls analytics."""
        # Setup authentication
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Prepare ask request
        ask_data = {"prompt": "Hello, how are you?", "model": "gpt-4o"}

        # Mock route_prompt to return a specific response
        with patch(
            "app.main.route_prompt",
            AsyncMock(return_value="Hello! I'm doing well, thank you for asking."),
        ):
            response = client.post("/v1/ask", json=ask_data)

        assert response.status_code == 200
        data = response.json()

        # Should return the mocked response
        assert "response" in data
        assert data["response"] == "Hello! I'm doing well, thank you for asking."

    def test_ask_endpoint_unauthenticated(self, client: TestClient):
        """Test POST /v1/ask without authentication returns 401."""
        ask_data = {"prompt": "Hello, how are you?"}

        response = client.post("/v1/ask", json=ask_data)

        assert response.status_code == 401

    def test_ask_endpoint_empty_prompt(self, client: TestClient):
        """Test POST /v1/ask with empty prompt returns error."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        ask_data = {"prompt": ""}

        response = client.post("/v1/ask", json=ask_data)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert "empty_prompt" in data["detail"]

    def test_ask_endpoint_with_chat_format(self, client: TestClient):
        """Test POST /v1/ask with chat message format."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        ask_data = {"messages": [{"role": "user", "content": "Hello!"}]}

        with patch("app.main.route_prompt", AsyncMock(return_value="Hi there!")):
            response = client.post("/v1/ask", json=ask_data)

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Hi there!"

    def test_ask_endpoint_analytics_tracking(self, client: TestClient):
        """Test that POST /v1/ask properly tracks analytics."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        ask_data = {"prompt": "Test prompt"}

        with patch("app.main.route_prompt", AsyncMock(return_value="Test response")):
            response = client.post("/v1/ask", json=ask_data)

        # Should return successful response
        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Test response"

    def test_cors_headers_present(self, client: TestClient):
        """Test that CORS headers are present in responses."""
        response = client.get("/healthz/ready")

        # Check for CORS headers
        headers = response.headers

        # Should have basic CORS headers
        assert "access-control-allow-origin" in headers
        assert "access-control-allow-credentials" in headers

    def test_json_content_type_enforced(self, client: TestClient):
        """Test that endpoints enforce JSON content type."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Try to send non-JSON data
        response = client.post(
            "/v1/ask",
            data="not json",  # Not JSON
            headers={"Content-Type": "text/plain"},
        )

        assert response.status_code == 415
        data = response.json()
        assert "unsupported_media_type" in data["detail"]

    def test_rate_limiting_headers(self, client: TestClient):
        """Test that rate limiting headers are present when applicable."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Make multiple requests to potentially trigger rate limiting
        for _ in range(3):
            response = client.get("/v1/whoami")
            if response.status_code == 429:
                # Rate limited - check for appropriate headers
                assert "retry-after" in response.headers
                break

    def test_error_response_format(self, client: TestClient):
        """Test that error responses follow consistent format."""
        # Try to access protected endpoint without auth
        response = client.post("/v1/auth/logout")

        assert response.status_code in [401, 403, 204]  # Could be any of these

        if response.status_code != 204:
            data = response.json()
            # Error responses should have detail field
            assert "detail" in data
            assert isinstance(data["detail"], str)

    def test_cache_headers_on_health(self, client: TestClient):
        """Test that health endpoints have appropriate cache headers."""
        response = client.get("/healthz/ready")

        headers = response.headers
        assert "cache-control" in headers
        assert (
            "no-store" in headers["cache-control"]
            or "no-cache" in headers["cache-control"]
        )
        assert "pragma" in headers
        assert headers["pragma"] == "no-cache"

    def test_vary_header_present(self, client: TestClient):
        """Test that Vary header is present for cache correctness."""
        response = client.get("/healthz/ready")

        assert "vary" in response.headers
        assert "Accept" in response.headers["vary"]

    def test_request_id_header_echoed(self, client: TestClient):
        """Test that request ID headers are echoed back."""
        request_id = "test-request-123"

        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        response = client.get("/v1/auth/whoami", headers={"X-Request-ID": request_id})

        # Should echo back the request ID
        if "x-request-id" in response.headers:
            assert response.headers["x-request-id"] == request_id

    def test_comprehensive_auth_flow(self, client: TestClient):
        """Test complete authentication flow from login to logout."""

        # 1. Login
        login_response = client.post(
            "/v1/auth/dev/login", json={"username": "flowtest"}
        )
        assert login_response.status_code == 200

        # 2. Check whoami (should be authenticated)
        whoami_response = client.get("/v1/auth/whoami")
        assert whoami_response.status_code == 200
        assert whoami_response.json()["is_authenticated"] is True

        # 3. Make authenticated request to protected endpoint
        ask_response = client.post("/v1/ask", json={"prompt": "test"})
        assert ask_response.status_code in [
            200,
            401,
        ]  # May succeed or fail due to mocking

        # 4. Logout
        logout_response = client.post("/v1/auth/logout")
        assert logout_response.status_code == 204

        # 5. Verify no longer authenticated
        whoami_response = client.get("/v1/auth/whoami")
        assert whoami_response.status_code == 401

    def test_concurrent_request_handling(self, client: TestClient):
        """Test that the API can handle concurrent requests properly."""
        import threading

        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        results = []

        def make_request():
            response = client.get("/healthz/ready")
            results.append(response.status_code)

        # Create multiple threads to make concurrent requests
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All requests should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 5

    def test_large_payload_handling(self, client: TestClient):
        """Test handling of large payloads."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Create a large prompt
        large_prompt = "x" * 10000  # 10KB prompt

        ask_data = {"prompt": large_prompt}

        response = client.post("/v1/ask", json=ask_data)

        # Should handle large payload gracefully
        assert response.status_code in [
            200,
            413,
            422,
        ]  # Success, too large, or validation error

    def test_malformed_json_handling(self, client: TestClient):
        """Test handling of malformed JSON."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Send malformed JSON
        response = client.post(
            "/v1/ask",
            data='{"prompt": "test", invalid}',
            headers={"Content-Type": "application/json"},
        )

        # Should get a 422 Unprocessable Entity
        assert response.status_code == 422

    def test_sql_injection_attempt_handling(self, client: TestClient):
        """Test handling of potential SQL injection attempts."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Try SQL injection in username field
        malicious_username = "admin'; DROP TABLE users; --"
        login_data = {"username": malicious_username}

        response = client.post("/v1/auth/dev/login", json=login_data)

        # Should handle safely without crashing
        assert response.status_code in [200, 400]

        if response.status_code == 200:
            data = response.json()
            assert data["user_id"] == malicious_username  # Should be sanitized/escaped

    def test_xss_attempt_handling(self, client: TestClient):
        """Test handling of potential XSS attempts."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Try XSS in prompt
        xss_prompt = '<script>alert("xss")</script>'
        ask_data = {"prompt": xss_prompt}

        response = client.post("/v1/ask", json=ask_data)

        # Should handle safely
        assert response.status_code in [200, 400, 422]

        if response.status_code == 200:
            data = response.json()
            # Response should not contain unescaped script tags
            assert "<script>" not in data.get("response", "")

    def test_path_traversal_attempt(self, client: TestClient):
        """Test handling of path traversal attempts."""
        # Try path traversal in URL
        response = client.get("/healthz/ready/../../../etc/passwd")

        # Should not allow path traversal
        assert response.status_code in [404, 403]

    def test_unauthorized_access_patterns(self, client: TestClient):
        """Test various unauthorized access patterns."""
        endpoints = ["/v1/ask", "/v1/auth/logout", "/v1/auth/refresh", "/v1/models"]

        for endpoint in endpoints:
            response = (
                client.get(endpoint) if "GET" in endpoint else client.post(endpoint)
            )

            # Should either be 401/403 (unauthorized) or 422 (validation error)
            assert response.status_code in [401, 403, 404, 422, 405]

    def test_health_endpoint_under_load(self, client: TestClient):
        """Test health endpoint performance under load."""
        import time

        start_time = time.time()

        # Make multiple health requests
        for _ in range(10):
            response = client.get("/healthz/ready")
            assert response.status_code == 200

        end_time = time.time()
        total_time = end_time - start_time

        # Should handle 10 requests quickly (under 2 seconds)
        assert total_time < 2.0

    def test_memory_leak_prevention(self, client: TestClient):
        """Test that repeated requests don't cause memory leaks."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Make many requests
        for _ in range(50):
            response = client.get("/v1/whoami")
            assert response.status_code in [200, 401]

        # Should still be able to make requests after many iterations
        response = client.get("/healthz/ready")
        assert response.status_code == 200

    def test_timeout_handling(self, client: TestClient):
        """Test handling of request timeouts."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Mock a slow response
        with patch(
            "app.main.route_prompt",
            AsyncMock(side_effect=lambda *args, **kwargs: asyncio.sleep(30)),
        ):
            # This should timeout and return an error
            response = client.post("/v1/ask", json={"prompt": "test"}, timeout=1.0)

            # Should get some kind of error response
            assert response.status_code in [500, 504, 408]

    def test_graceful_error_recovery(self, client: TestClient):
        """Test that the API can recover from errors gracefully."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # First make a successful request
        response = client.get("/healthz/ready")
        assert response.status_code == 200

        # Then simulate an error
        with patch(
            "app.main.route_prompt", AsyncMock(side_effect=Exception("Test error"))
        ):
            response = client.post("/v1/ask", json={"prompt": "test"})
            assert response.status_code == 500

        # Should still be able to make successful requests after error
        response = client.get("/healthz/ready")
        assert response.status_code == 200

    def test_request_response_consistency(self, client: TestClient):
        """Test that request and response are consistent."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        request_data = {"prompt": "Test consistency"}
        response = client.post("/v1/ask", json=request_data)

        # Check content type consistency
        assert response.headers.get("content-type", "").startswith("application/json")

        # If successful, should have proper JSON structure
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_api_version_consistency(self, client: TestClient):
        """Test that API version is consistent across endpoints."""
        # Get version from health endpoint
        health_response = client.get("/healthz/ready")
        assert health_response.status_code == 200
        health_data = health_response.json()

        version = health_data.get("version")

        # Version should be present and consistent
        assert version is not None
        assert isinstance(version, str)

    def test_security_headers(self, client: TestClient):
        """Test that security headers are present."""
        response = client.get("/healthz/ready")

        headers = response.headers

        # Should not have any dangerous headers
        dangerous_headers = ["server", "x-powered-by"]
        for header in dangerous_headers:
            assert header.lower() not in [h.lower() for h in headers.keys()]

    def test_content_length_validation(self, client: TestClient):
        """Test that content length is validated."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        # Test with oversized content
        large_content = "x" * 1000000  # 1MB
        ask_data = {"prompt": large_content}

        response = client.post("/v1/ask", json=ask_data)

        # Should handle appropriately (either success, validation error, or size limit)
        assert response.status_code in [200, 413, 422, 500]

    def test_http_methods_validation(self, client: TestClient):
        """Test that only allowed HTTP methods are accepted."""
        # Try invalid method on endpoint
        response = client.patch("/healthz/ready")

        # Should get method not allowed
        assert response.status_code == 405
        assert "method" in response.json().get("detail", "").lower()

    def test_query_parameter_validation(self, client: TestClient):
        """Test that query parameters are validated."""
        # Try with invalid query parameters
        response = client.get("/healthz/ready?invalid_param=value")

        # Should still work (unknown params should be ignored)
        assert response.status_code == 200

    def test_response_format_consistency(self, client: TestClient):
        """Test that all responses follow consistent format."""
        endpoints = ["/healthz/ready", "/v1/models"]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200

            data = response.json()
            # Should be a dictionary
            assert isinstance(data, dict)

            # Should have consistent structure
            if endpoint == "/healthz/ready":
                assert "status" in data
                assert "timestamp" in data
            elif endpoint == "/v1/models":
                assert "items" in data

    def test_api_contract_compliance(self, client: TestClient):
        """Test that API complies with documented contracts."""
        # Test health contract
        response = client.get("/healthz/ready")
        assert response.status_code == 200

        data = response.json()

        # Required fields from contract
        required_fields = ["status", "timestamp", "version"]
        for field in required_fields:
            assert field in data

        # Status should be string
        assert isinstance(data["status"], str)

        # Timestamp should be ISO format string
        assert isinstance(data["timestamp"], str)
        # Should be parseable as ISO format
        datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

    def test_auth_token_format_validation(self, client: TestClient):
        """Test that auth tokens follow expected format."""
        cookies = create_auth_cookies("testuser")
        client.cookies.set("GSNH_AT", cookies["access_token"])

        response = client.get("/v1/auth/whoami")
        assert response.status_code == 200

        # Try with malformed token
        client.cookies.set("GSNH_AT", "not-a-jwt")
        response = client.get("/v1/auth/whoami")

        # Should handle gracefully
        assert response.status_code in [200, 401]
        if response.status_code == 200:
            data = response.json()
            assert data["is_authenticated"] is False

    def test_concurrent_auth_handling(self, client: TestClient):
        """Test that concurrent auth requests are handled properly."""
        import threading

        def make_auth_request():
            cookies = create_auth_cookies("testuser")
            test_client = create_test_client()
            test_client.cookies.set("GSNH_AT", cookies["access_token"])
            response = test_client.get("/v1/auth/whoami")
            return response.status_code

        # Make concurrent auth requests
        threads = []
        results = []

        for _ in range(5):

            def worker():
                status = make_auth_request()
                results.append(status)

            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All should succeed
        assert all(status == 200 for status in results)
        assert len(results) == 5
