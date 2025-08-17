"""Test that OPTIONS requests to /v1/auth/refresh are handled correctly by CORS middleware."""

import pytest
from fastapi.testclient import TestClient


def test_options_refresh_without_cors_headers(client: TestClient):
    """Test that simple OPTIONS request returns 405 Method Not Allowed."""
    response = client.options("/v1/auth/refresh")
    assert response.status_code == 405
    # Should indicate that only POST is allowed
    assert "POST" in response.headers.get("allow", "")


def test_options_refresh_with_cors_headers(client: TestClient):
    """Test that CORS preflight OPTIONS request returns 200 with CORS headers."""
    headers = {
        "Origin": "http://127.0.0.1:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-auth-intent"
    }
    response = client.options("/v1/auth/refresh", headers=headers)
    assert response.status_code == 200
    # Should have CORS headers for preflight request
    assert "access-control-allow-origin" in response.headers
    assert "access-control-allow-methods" in response.headers
    assert "access-control-allow-headers" in response.headers
    assert "access-control-allow-credentials" in response.headers
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "x-auth-intent" in response.headers["access-control-allow-headers"]


def test_options_refresh_cors_credentials(client: TestClient):
    """Test that CORS preflight includes credentials support."""
    headers = {
        "Origin": "http://127.0.0.1:3000",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-auth-intent"
    }
    response = client.options("/v1/auth/refresh", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-credentials"] == "true"
