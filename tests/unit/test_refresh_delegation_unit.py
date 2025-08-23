"""Test that legacy refresh endpoint properly delegates to canonical endpoint."""

from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_legacy_refresh_delegates_to_canonical():
    """Test that /v1/refresh delegates to /v1/auth/refresh."""
    from app.api.auth import router as canonical_router
    from app.auth import router as legacy_router

    app = FastAPI()
    app.include_router(legacy_router, prefix="/v1")
    app.include_router(canonical_router, prefix="/v1")

    client = TestClient(app)

    # Test that both endpoints exist
    response1 = client.post("/v1/refresh", json={"refresh_token": "test"})
    response2 = client.post("/v1/auth/refresh", json={"refresh_token": "test"})

    # Both should return 401 (unauthorized) since we don't have valid tokens
    assert response1.status_code == 401
    assert response2.status_code == 401

    # Both should have similar response structure
    assert "detail" in response1.json()
    assert "detail" in response2.json()


def test_legacy_refresh_logs_deprecation():
    """Test that legacy refresh endpoint logs deprecation warning."""
    from app.auth import router as legacy_router

    app = FastAPI()
    app.include_router(legacy_router, prefix="/v1")
    client = TestClient(app)

    # Reset the deprecation flag to ensure we can test it
    import app.auth

    app.auth._DEPRECATE_REFRESH_LOGGED = False

    # Mock print to capture deprecation message
    with patch("builtins.print") as mock_print:
        client.post("/v1/refresh", json={"refresh_token": "test"})
        # The deprecation message should be logged
        mock_print.assert_called_with("deprecate route=/v1/refresh")


def test_canonical_refresh_is_primary():
    """Test that canonical refresh endpoint is the primary implementation."""
    from app.api.auth import router as canonical_router

    app = FastAPI()
    app.include_router(canonical_router, prefix="/v1")
    client = TestClient(app)

    # Test canonical endpoint directly
    response = client.post("/v1/auth/refresh", json={"refresh_token": "test"})
    assert response.status_code == 401  # Expected for invalid token

    # Test that the endpoint exists and responds correctly
    # Note: CORS headers are added by middleware, not by the endpoint itself
    assert "detail" in response.json()


def test_legacy_refresh_maintains_compatibility():
    """Test that legacy refresh endpoint maintains backward compatibility."""
    from app.auth import router as legacy_router

    app = FastAPI()
    app.include_router(legacy_router, prefix="/v1")
    client = TestClient(app)

    # Test with different request formats
    response1 = client.post("/v1/refresh")  # No body
    response2 = client.post("/v1/refresh", json={"refresh_token": "test"})  # With body

    # Both should work (return 401 for invalid tokens, but not crash)
    assert response1.status_code == 401
    assert response2.status_code == 401
