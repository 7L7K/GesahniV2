"""Test CORS production features: allowlist enforcement and metrics."""
import os
from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from app.main import create_app
from app.middleware.cors import get_cors_metrics, _is_production_mode, _get_allowed_origins


def test_cors_production_mode_detection():
    """Test production mode detection."""
    # Test with ENV=prod
    with patch.dict(os.environ, {"ENV": "prod"}):
        assert _is_production_mode() is True

    # Test with PRODUCTION=1
    with patch.dict(os.environ, {"PRODUCTION": "1"}):
        assert _is_production_mode() is True

    # Test development mode
    with patch.dict(os.environ, {}, clear=True):
        assert _is_production_mode() is False


def test_cors_allowlist_production_validation():
    """Test production CORS allowlist validation."""
    # Test production mode with explicit origins
    with patch.dict(os.environ, {"ENV": "prod", "CORS_ALLOW_ORIGINS": "https://app.example.com,https://admin.example.com"}):
        origins = _get_allowed_origins()
        assert "https://app.example.com" in origins
        assert "https://admin.example.com" in origins
        assert len(origins) == 2

    # Test production mode rejects wildcards
    with patch.dict(os.environ, {"ENV": "prod", "CORS_ALLOW_ORIGINS": "https://app.example.com,*"}):
        origins = _get_allowed_origins()
        assert "https://app.example.com" in origins
        assert "*" not in origins
        assert len(origins) == 1

    # Test production mode rejects invalid schemes
    with patch.dict(os.environ, {"ENV": "prod", "CORS_ALLOW_ORIGINS": "https://app.example.com,ftp://example.com"}):
        origins = _get_allowed_origins()
        assert "https://app.example.com" in origins
        assert "ftp://example.com" not in origins
        assert len(origins) == 1


def test_cors_development_defaults():
    """Test development CORS defaults."""
    with patch.dict(os.environ, {}, clear=True):  # Development mode
        origins = _get_allowed_origins()
        assert "http://localhost:3000" in origins
        assert "http://127.0.0.1:3000" in origins


def test_cors_preflight_rejection_metrics():
    """Test CORS preflight rejection metrics."""
    from app.middleware.cors import _cors_rejected_origins, _cors_rejected_count

    # Reset metrics
    _cors_rejected_origins.clear()
    _cors_rejected_count = 0

    # Configure production mode with restricted origins BEFORE creating app
    with patch.dict(os.environ, {
        "ENV": "prod",
        "CORS_ORIGINS": "https://allowed.example.com"
    }):
        # Test metrics collection
        app = create_app()
        client = TestClient(app)

        # Test preflight rejection
        response = client.options(
            "/v1/me",
            headers={
                "Origin": "https://malicious.example.com",
                "Access-Control-Request-Method": "GET"
            }
        )

        assert response.status_code == 400

        # Check metrics
        metrics = get_cors_metrics()
        assert "https://malicious.example.com" in metrics["rejected_origins"]
        assert metrics["rejected_count"] >= 1


def test_cors_production_explicit_origins_only():
    """Test that production mode only allows explicit origins."""
    app = create_app()

    with patch.dict(os.environ, {
        "ENV": "prod",
        "CORS_ALLOW_ORIGINS": "https://allowed.example.com"
    }):
        client = TestClient(app)

        # Test allowed origin
        response = client.get(
            "/health",
            headers={"Origin": "https://allowed.example.com"}
        )
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == "https://allowed.example.com"

        # Test rejected origin (should not get CORS headers)
        response = client.get(
            "/health",
            headers={"Origin": "https://rejected.example.com"}
        )
        assert response.status_code == 200
        # Should not have CORS headers for rejected origin
        assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_preflight_cache_production():
    """Test preflight cache duration in production."""
    from app.middleware.cors import _get_preflight_max_age

    # Test production default
    with patch.dict(os.environ, {"ENV": "prod"}):
        assert _get_preflight_max_age() == 3600  # 1 hour

    # Test custom production value
    with patch.dict(os.environ, {"ENV": "prod", "CORS_MAX_AGE": "7200"}):
        assert _get_preflight_max_age() == 7200

    # Test development default
    with patch.dict(os.environ, {}, clear=True):
        assert _get_preflight_max_age() == 600  # 10 minutes


def test_cors_metrics_functionality():
    """Test CORS metrics collection."""
    from app.middleware.cors import _cors_rejected_origins, _cors_rejected_count

    # Reset metrics
    _cors_rejected_origins.clear()
    _cors_rejected_count = 0

    # Simulate rejections
    _cors_rejected_origins.add("https://bad1.example.com")
    _cors_rejected_origins.add("https://bad2.example.com")
    _cors_rejected_count = 3

    metrics = get_cors_metrics()
    assert len(metrics["rejected_origins"]) == 2
    assert metrics["rejected_count"] == 3
    assert "https://bad1.example.com" in metrics["rejected_origins"]
    assert "https://bad2.example.com" in metrics["rejected_origins"]
