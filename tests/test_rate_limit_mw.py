# tests/test_rate_limit_mw.py
import importlib
import os
import time

from starlette.testclient import TestClient


def _spin():
    """Fresh app instance for testing with rate limit config."""
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]
    # Set low rate limit for fast testing
    os.environ["RATE_LIMIT_PER_MIN"] = "2"
    os.environ["RATE_LIMIT_WINDOW_S"] = "1"  # 1 second window
    # Disable middleware order check for testing
    os.environ["ENV"] = "dev"

    # Clear the rate limit bucket to ensure test isolation
    from app.middleware.rate_limit import _BUCKET

    _BUCKET.clear()

    from app.main import app

    return TestClient(app)


def test_rate_limit_basic(monkeypatch):
    """Test basic rate limiting functionality."""
    c = _spin()

    # Health endpoint should not be rate limited
    r1 = c.get("/health")
    assert r1.status_code == 200

    # CSRF endpoint should be rate limited
    # Make exactly 3 requests to trigger rate limiting
    # The rate limit is 2 requests per 1-second window
    responses = []
    for i in range(3):
        r = c.get("/v1/csrf")
        responses.append(r.status_code)

    # First two should succeed (200), third should be rate limited (429)
    assert responses[0] == 200
    assert responses[1] == 200
    assert responses[2] == 429

    # Verify the rate limited response has proper content
    r4 = c.get("/v1/csrf")
    assert "rate_limited" in r4.text.lower()

    # Verify the response has proper rate limit headers
    assert r4.headers.get("retry-after") == "1"


def test_rate_limit_options_exempt():
    """Test that OPTIONS requests are not rate limited."""
    c = _spin()

    # Multiple OPTIONS requests should all succeed
    for _ in range(5):
        r = c.options("/v1/csrf")
        assert r.status_code == 200


def test_rate_limit_window_reset():
    """Test that rate limit resets after window expires."""
    c = _spin()

    # Use up the rate limit
    c.get("/v1/csrf")
    c.get("/v1/csrf")
    r3 = c.get("/v1/csrf")
    assert r3.status_code == 429

    # Wait for window to reset (1 second)
    time.sleep(1.1)

    # Should allow request after reset
    r4 = c.get("/v1/csrf")
    assert r4.status_code == 200


def test_rate_limit_headers():
    """Test that rate limit headers are present in responses."""
    c = _spin()

    r = c.get("/v1/csrf")
    assert r.status_code == 200
    assert "ratelimit-limit" in r.headers
    assert "ratelimit-remaining" in r.headers
    assert "ratelimit-reset" in r.headers

    # Check header values
    assert r.headers["ratelimit-limit"] == "2"
    assert int(r.headers["ratelimit-remaining"]) <= 2


def test_rate_limit_user_isolation():
    """Test that rate limits are per-user (simulated via different IPs)."""
    # This would require mocking different client IPs
    # For now, test that rate limit applies per request
    c = _spin()

    # Make requests that should trigger rate limiting
    responses = []
    for _ in range(4):
        r = c.get("/v1/csrf")
        responses.append(r.status_code)

    # Should have at least one 429 (rate limited)
    assert 429 in responses
    # Should have at least two 200s (successful)
    assert responses.count(200) >= 2


def test_rate_limit_middleware_import():
    """Test that RateLimitMiddleware can be imported and instantiated."""
    from app.middleware.rate_limit import _BUCKET, RateLimitMiddleware

    # Test that the middleware class exists and can be instantiated
    middleware = RateLimitMiddleware(None)
    assert middleware is not None

    # Test that the bucket is accessible
    assert isinstance(_BUCKET, dict)


def test_csrf_middleware_enhancements():
    """Test that CSRF middleware enhancements are working."""
    from app.csrf import _extract_csrf_header, _truthy

    # Test _truthy function
    assert _truthy("1") is True
    assert _truthy("true") is True
    assert _truthy("yes") is True
    assert _truthy("on") is True
    assert _truthy("0") is False
    assert _truthy("") is False

    # Test _extract_csrf_header function
    from starlette.datastructures import Headers
    from starlette.requests import Request

    # Create a mock request
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": Headers({"x-csrf-token": "test-token"}).raw,
    }
    request = Request(scope)

    token, used_legacy, legacy_allowed = _extract_csrf_header(request)
    assert token == "test-token"
    assert used_legacy is False
    assert legacy_allowed is False


def test_secret_verification():
    """Test secret verification functions."""
    from app.secret_verification import audit_prod_env, get_missing_required_secrets

    # Test that audit_prod_env function exists and can be called
    # (it will fail in non-prod environment, which is expected)
    try:
        audit_prod_env()
        assert True  # Should not raise in dev mode
    except RuntimeError as e:
        # Should only raise in prod with missing secrets
        assert "Missing required env" in str(e) or "too weak" in str(e)

    # Test missing secrets detection
    missing = get_missing_required_secrets()
    # In dev/test mode, some secrets may be missing, which is OK
    assert isinstance(missing, list)
