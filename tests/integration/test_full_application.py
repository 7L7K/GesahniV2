"""
Integration tests that verify the full application works end-to-end.
These tests start the actual server and make HTTP requests.
"""
import os
import signal
import subprocess
import sys
import time
from contextlib import contextmanager

import pytest
import requests


@contextmanager
def running_server(port=8010):
    """Context manager that starts the server and cleans it up."""
    # Start the server
    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:create_app",
        "--host", "127.0.0.1",
        "--port", str(port),
        "--reload"
    ]

    env = os.environ.copy()
    env["CI"] = "1"  # Ensure CI mode for consistent behavior

    proc = subprocess.Popen(
        cmd,
        env=env,
        preexec_fn=os.setsid,  # Create new process group
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        # Wait for server to start
        time.sleep(3)

        # Test that server is responding
        response = requests.get(f"http://127.0.0.1:{port}/health", timeout=5)
        assert response.status_code == 200, "Server should be responding"

        yield f"http://127.0.0.1:{port}"

    finally:
        # Clean shutdown
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            proc.kill()
            proc.wait(timeout=5)


@pytest.mark.integration
def test_full_application_startup():
    """Test that the full application starts up correctly."""
    with running_server() as base_url:
        # Test basic endpoints
        endpoints = [
            "/health",
            "/openapi.json",
            "/",
        ]

        for endpoint in endpoints:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            assert response.status_code in [200, 404], f"Endpoint {endpoint} should respond"


@pytest.mark.integration
def test_api_routes_function():
    """Test that API routes are working."""
    with running_server() as base_url:
        # Test 404 error handling
        response = requests.get(f"{base_url}/nonexistent", timeout=5)
        assert response.status_code == 404

        # Check error response format
        error_data = response.json()
        assert "code" in error_data, "Error response should have code field"
        assert "message" in error_data, "Error response should have message field"
        assert "details" in error_data, "Error response should have details field"


@pytest.mark.integration
def test_cors_preflight():
    """Test CORS preflight requests work."""
    with running_server() as base_url:
        # Test OPTIONS request
        response = requests.options(
            f"{base_url}/v1/ask",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
            timeout=5
        )

        assert response.status_code in [200, 204], "OPTIONS request should succeed"

        # Check CORS headers
        cors_headers = [
            "access-control-allow-origin",
            "access-control-allow-methods",
            "access-control-allow-headers"
        ]

        response_headers_lower = {k.lower(): v for k, v in response.headers.items()}
        for header in cors_headers:
            assert header in response_headers_lower, f"CORS header {header} should be present"


@pytest.mark.integration
def test_openapi_schema_accessible():
    """Test that OpenAPI schema is accessible and valid."""
    with running_server() as base_url:
        response = requests.get(f"{base_url}/openapi.json", timeout=5)
        assert response.status_code == 200, "OpenAPI schema should be accessible"

        schema = response.json()

        # Basic schema validation
        required_fields = ["openapi", "info", "paths"]
        for field in required_fields:
            assert field in schema, f"Schema should have {field} field"

        # Should have some paths
        assert len(schema["paths"]) > 0, "Schema should have some paths"

        # Should have info
        assert "title" in schema["info"], "Schema should have title"
        assert "version" in schema["info"], "Schema should have version"


@pytest.mark.integration
def test_rate_limiting_disabled_in_ci():
    """Test that rate limiting is disabled in CI mode."""
    with running_server() as base_url:
        # Make multiple requests quickly
        responses = []
        for i in range(10):
            response = requests.get(f"{base_url}/health", timeout=5)
            responses.append(response)

        # All should succeed (no rate limiting)
        success_count = sum(1 for r in responses if r.status_code == 200)
        assert success_count == len(responses), "All requests should succeed in CI mode"

        # Check that rate limit headers are not present
        last_response = responses[-1]
        rate_limit_headers = [
            "x-ratelimit-limit",
            "x-ratelimit-remaining",
            "x-ratelimit-reset"
        ]

        response_headers_lower = {k.lower(): v for k, v in last_response.headers.items()}
        for header in rate_limit_headers:
            assert header not in response_headers_lower, f"Rate limit header {header} should not be present in CI"


@pytest.mark.integration
def test_request_id_header():
    """Test that request ID headers are added to responses."""
    with running_server() as base_url:
        response = requests.get(f"{base_url}/health", timeout=5)

        # Should have X-Request-ID header
        assert "x-request-id" in response.headers, "Response should have X-Request-ID header"

        request_id = response.headers["x-request-id"]
        assert len(request_id) > 0, "Request ID should not be empty"


@pytest.mark.integration
def test_error_response_format():
    """Test that error responses have consistent format."""
    with running_server() as base_url:
        # Test 404
        response = requests.get(f"{base_url}/nonexistent", timeout=5)
        assert response.status_code == 404

        error_data = response.json()

        # Check required fields
        required_fields = ["code", "message", "details"]
        for field in required_fields:
            assert field in error_data, f"Error response should have {field} field"

        # Check details structure
        details = error_data["details"]
        assert "status_code" in details, "Details should have status_code"
        assert "path" in details, "Details should have path"
        assert "method" in details, "Details should have method"

        # Check that X-Error-Code header is present
        assert "x-error-code" in response.headers, "Response should have X-Error-Code header"


@pytest.mark.integration
def test_health_endpoint_structure():
    """Test that health endpoint returns expected structure."""
    with running_server() as base_url:
        response = requests.get(f"{base_url}/health", timeout=5)
        assert response.status_code == 200

        health_data = response.json()

        # Health should have timestamp
        assert "timestamp" in health_data, "Health response should have timestamp"

        # Should have some status information
        assert len(health_data) > 1, "Health response should have multiple fields"


@pytest.mark.integration
def test_v1_routes_exist():
    """Test that v1 API routes exist."""
    with running_server() as base_url:
        # Test some core v1 routes
        routes_to_test = [
            "/v1/ask",
            "/v1/auth",
            "/v1/admin"
        ]

        for route in routes_to_test:
            # For routes that require authentication, we expect 401/403
            response = requests.post(f"{base_url}{route}", json={}, timeout=5)
            # Should get auth error or validation error, not 404
            assert response.status_code != 404, f"Route {route} should exist (got 404)"
