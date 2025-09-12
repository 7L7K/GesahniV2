#!/usr/bin/env python3
"""Test script to verify deprecation signaling on compat endpoints."""

import asyncio
import logging
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.router.compat_api import DeprecationRedirectResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_deprecation_headers():
    """Test that DeprecationRedirectResponse adds correct headers."""
    logger.info("🧪 Testing DeprecationRedirectResponse headers...")

    # Test with successor version
    response = DeprecationRedirectResponse(
        url="/v1/test",
        successor_version="/v1/test",
        sunset_date="2025-12-31"
    )

    assert response.headers.get("Deprecation") == "true"
    assert response.headers.get("Sunset") == "2025-12-31"
    assert response.headers.get("Link") == '</v1/test>; rel="successor-version"'
    assert response.status_code == 308

    logger.info("✅ DeprecationRedirectResponse headers test passed")


def test_compat_endpoints_headers():
    """Test that compat endpoints return proper deprecation headers."""
    logger.info("🧪 Testing compat endpoints deprecation headers...")

    from app.router.compat_api import router

    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)

    # Test GET compat endpoints only
    test_endpoints = [
        ("/whoami", "/v1/whoami"),
        ("/health", "/v1/health"),
        ("/healthz", "/v1/healthz"),
        ("/status", "/v1/status"),
    ]

    for endpoint, expected_redirect in test_endpoints:
        logger.info(f"Testing endpoint: {endpoint}")

        # Test GET request
        response = client.get(endpoint, allow_redirects=False)

        # Should return 308 redirect
        assert response.status_code == 308, f"Expected 308 for {endpoint}, got {response.status_code}"

        # Check deprecation headers
        assert response.headers.get("Deprecation") == "true", f"Missing Deprecation header for {endpoint}"
        assert response.headers.get("Sunset") == "2025-12-31", f"Wrong Sunset header for {endpoint}: {response.headers.get('Sunset')}"
        assert response.headers.get("Link") == f'<{expected_redirect}>; rel="successor-version"', f"Wrong Link header for {endpoint}"

        # Check redirect location
        assert response.headers.get("Location") == expected_redirect, f"Wrong redirect location for {endpoint}"

        logger.info(f"✅ {endpoint} deprecation headers correct")

    logger.info("✅ All compat endpoints deprecation headers test passed")


def test_post_endpoints():
    """Test POST endpoints that also support deprecation."""
    logger.info("🧪 Testing POST compat endpoints...")

    from app.router.compat_api import router

    app = FastAPI()
    app.include_router(router)

    client = TestClient(app)

    # Test POST endpoints
    post_endpoints = [
        ("/ask", "/v1/ask"),
        ("/v1/login", "/v1/auth/login"),
        ("/v1/register", "/v1/auth/register"),
    ]

    for endpoint, expected_redirect in post_endpoints:
        logger.info(f"Testing POST endpoint: {endpoint}")

        response = client.post(endpoint, allow_redirects=False)

        assert response.status_code == 308, f"Expected 308 for POST {endpoint}, got {response.status_code}"
        assert response.headers.get("Deprecation") == "true", f"Missing Deprecation header for POST {endpoint}"
        assert response.headers.get("Sunset") == "2025-12-31", f"Wrong Sunset header for POST {endpoint}"
        assert response.headers.get("Location") == expected_redirect, f"Wrong redirect location for POST {endpoint}"

        logger.info(f"✅ POST {endpoint} deprecation headers correct")

    logger.info("✅ All POST compat endpoints test passed")


if __name__ == "__main__":
    logger.info("🚀 Starting deprecation signaling tests")

    try:
        test_deprecation_headers()
        test_compat_endpoints_headers()
        test_post_endpoints()

        logger.info("🎉 All deprecation signaling tests passed!")
        exit(0)

    except Exception as e:
        logger.error(f"💥 Test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
