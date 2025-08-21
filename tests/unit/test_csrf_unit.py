from __future__ import annotations

import os
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from starlette.middleware.cors import CORSMiddleware
import pytest
import asyncio

from app.csrf import CSRFMiddleware, get_csrf_token, _extract_csrf_header


def _app():
    # Explicitly set CSRF_ENABLED to ensure it's enabled
    os.environ["CSRF_ENABLED"] = "1"
    a = FastAPI()

    # Add CORS middleware first (handles preflights)
    a.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Add CSRF middleware after CORS (handles non-OPTIONS requests)
    a.add_middleware(CSRFMiddleware)

    @a.get("/ping")
    async def ping():
        return {"ok": True}

    @a.head("/head")
    async def head():
        return {"ok": True}

    @a.post("/post")
    async def post():
        return {"ok": True}

    @a.put("/put")
    async def put():
        return {"ok": True}

    @a.patch("/patch")
    async def patch_endpoint():
        return {"ok": True}

    @a.delete("/delete")
    async def delete():
        return {"ok": True}

    @a.options("/options")
    async def options():
        return {"ok": True}

    @a.post("/auth/oauth/callback")
    async def oauth_callback():
        return {"ok": True}

    @a.post("/auth/apple/callback")
    async def apple_callback():
        return {"ok": True}

    return a


# Test GET/HEAD exemption
def test_csrf_exempts_get_requests():
    c = TestClient(_app())
    assert c.get("/ping").status_code == 200


def test_csrf_exempts_head_requests():
    c = TestClient(_app())
    assert c.head("/head").status_code == 200


def test_csrf_exempts_options_requests():
    c = TestClient(_app())
    assert c.options("/options").status_code == 200


def test_csrf_blocks_post_without_token():
    c = TestClient(_app())
    r = c.post("/post")
    assert r.status_code == 403
    assert "invalid_csrf" in r.json()["detail"]


def test_csrf_blocks_put_without_token():
    c = TestClient(_app())
    r = c.put("/put")
    assert r.status_code == 403


def test_csrf_blocks_patch_without_token():
    c = TestClient(_app())
    r = c.patch("/patch")
    assert r.status_code == 403


def test_csrf_blocks_delete_without_token():
    c = TestClient(_app())
    r = c.delete("/delete")
    assert r.status_code == 403


# Test token issue/verify roundtrip
def test_csrf_token_roundtrip_matching():
    c = TestClient(_app())
    # Set cookie and header to same token
    t = "abc123"
    c.cookies.set("csrf_token", t)
    r = c.post("/post", headers={"X-CSRF-Token": t})
    assert r.status_code == 200


def test_csrf_token_mismatch():
    c = TestClient(_app())
    c.cookies.set("csrf_token", "cookie_token")
    r = c.post("/post", headers={"X-CSRF-Token": "header_token"})
    assert r.status_code == 403
    assert "invalid_csrf" in r.json()["detail"]


def test_csrf_missing_header_with_cookie():
    c = TestClient(_app())
    c.cookies.set("csrf_token", "some_token")
    r = c.post("/post")  # No header
    assert r.status_code == 403
    assert "invalid_csrf" in r.json()["detail"]


def test_csrf_missing_cookie_with_header():
    c = TestClient(_app())
    r = c.post("/post", headers={"X-CSRF-Token": "some_token"})  # No cookie
    assert r.status_code == 403
    assert "invalid_csrf" in r.json()["detail"]


# Test legacy header support
def test_csrf_legacy_header_allowed():
    with patch.dict(os.environ, {"CSRF_LEGACY_GRACE": "1"}):
        c = TestClient(_app())
        t = "legacy_token"
        c.cookies.set("csrf_token", t)
        r = c.post("/post", headers={"X-CSRF": t})  # Legacy header
        assert r.status_code == 200


def test_csrf_legacy_header_disabled():
    with patch.dict(os.environ, {"CSRF_LEGACY_GRACE": "0"}):
        c = TestClient(_app())
        c.cookies.set("csrf_token", "some_token")
        r = c.post("/post", headers={"X-CSRF": "some_token"})  # Legacy header
        assert r.status_code == 400
        assert "missing_csrf" in r.json()["detail"]


# Test cross-site vs same-site scenarios
def test_csrf_cross_site_validation():
    """Test CSRF validation in cross-site scenario (COOKIE_SAMESITE=none)."""
    with patch.dict(os.environ, {"COOKIE_SAMESITE": "none"}):
        c = TestClient(_app())

        # Missing header in cross-site scenario
        r = c.post("/post")
        assert r.status_code == 400
        assert "missing_csrf_cross_site" in r.json()["detail"]

        # Valid cross-site token
        t = "cross_site_token_16_chars"  # Must be >= 16 chars
        r = c.post("/post", headers={"X-CSRF-Token": t})
        assert r.status_code == 200

        # Invalid format (too short)
        r = c.post("/post", headers={"X-CSRF-Token": "short"})
        assert r.status_code == 403
        assert "invalid_csrf_format" in r.json()["detail"]


def test_csrf_same_site_validation():
    """Test CSRF validation in same-site scenario (default)."""
    c = TestClient(_app())

    # Missing both header and cookie
    r = c.post("/post")
    assert r.status_code == 403
    assert "invalid_csrf" in r.json()["detail"]

    # Valid same-site tokens
    t = "same_site_token"
    c.cookies.set("csrf_token", t)
    r = c.post("/post", headers={"X-CSRF-Token": t})
    assert r.status_code == 200


# Test OAuth callback bypass
def test_csrf_bypass_oauth_callback():
    c = TestClient(_app())
    # OAuth callback should bypass CSRF even without token - use the correct Apple callback path
    r = c.post("/auth/apple/callback")
    assert r.status_code == 200


# Test Bearer token bypass
def test_csrf_bypass_bearer_token():
    c = TestClient(_app())
    # Bearer token should bypass CSRF even without CSRF token
    r = c.post("/post", headers={"Authorization": "Bearer some_token"})
    assert r.status_code == 200


# Test CSRF disabled globally
def test_csrf_disabled_globally():
    # Create app with CSRF disabled by patching the environment check
    with patch("app.csrf._truthy") as mock_truthy:
        mock_truthy.return_value = False  # CSRF is disabled
        app = _app()
        c = TestClient(app)
        # Should allow POST without token when disabled
        r = c.post("/post")
        assert r.status_code == 200


# Test origin/referer checks (covered by cross-site/same-site tests above)


# Test get_csrf_token function
@pytest.mark.asyncio
async def test_get_csrf_token():
    """Test the get_csrf_token function returns a random token."""
    token1 = await get_csrf_token()
    token2 = await get_csrf_token()

    # Should return different tokens each time
    assert token1 != token2
    # Should be URL-safe strings
    assert len(token1) == 22  # 16 bytes * 4/3 for base64url (actual length with padding)
    assert len(token2) == 22


# Test _extract_csrf_header function
def test_extract_csrf_header_prefers_new_header():
    """Test that X-CSRF-Token is preferred over legacy X-CSRF."""
    mock_request = Mock(spec=Request)
    mock_request.headers = {
        "X-CSRF-Token": "new_token",
        "X-CSRF": "legacy_token"
    }

    with patch("app.csrf.os.getenv", return_value="1"):  # Legacy grace enabled
        token, used_legacy, legacy_allowed = _extract_csrf_header(mock_request)

    assert token == "new_token"
    assert used_legacy is False
    assert legacy_allowed is False


def test_extract_csrf_header_fallback_to_legacy():
    """Test fallback to legacy header when new header not present."""
    mock_request = Mock(spec=Request)
    mock_request.headers = {"X-CSRF": "legacy_token"}

    with patch("app.csrf.os.getenv", return_value="1"):  # Legacy grace enabled
        token, used_legacy, legacy_allowed = _extract_csrf_header(mock_request)

    assert token == "legacy_token"
    assert used_legacy is True
    assert legacy_allowed is True


def test_extract_csrf_header_no_token():
    """Test when no CSRF header is present."""
    mock_request = Mock(spec=Request)
    mock_request.headers = {}

    token, used_legacy, legacy_allowed = _extract_csrf_header(mock_request)

    assert token is None
    assert used_legacy is False
    assert legacy_allowed is False


def test_extract_csrf_header_legacy_disabled():
    """Test legacy header when grace period is disabled."""
    mock_request = Mock(spec=Request)
    mock_request.headers = {"X-CSRF": "legacy_token"}

    with patch("app.csrf.os.getenv", return_value="0"):  # Legacy grace disabled
        token, used_legacy, legacy_allowed = _extract_csrf_header(mock_request)

    assert token == "legacy_token"
    assert used_legacy is True
    assert legacy_allowed is False


# Test concurrent access
def test_csrf_concurrent_requests():
    """Test CSRF middleware handles concurrent requests properly."""
    import threading
    import time

    c = TestClient(_app())
    results = []

    def make_request(token_id):
        t = f"token_{token_id}"
        c.cookies.set("csrf_token", t)
        r = c.post("/post", headers={"X-CSRF-Token": t})
        results.append(r.status_code)

    # Run concurrent requests
    threads = []
    for i in range(10):
        thread = threading.Thread(target=make_request, args=(i,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # All requests should succeed
    assert all(status == 200 for status in results)


# Test malformed requests
def test_csrf_malformed_header():
    """Test handling of malformed CSRF headers."""
    c = TestClient(_app())

    # Empty header
    c.cookies.set("csrf_token", "valid_token")
    r = c.post("/post", headers={"X-CSRF-Token": ""})
    assert r.status_code == 403

    # Very long header
    long_token = "a" * 1000
    c.cookies.set("csrf_token", long_token)
    r = c.post("/post", headers={"X-CSRF-Token": long_token})
    assert r.status_code == 200  # Should still work if tokens match

    # Token with special characters
    special_token = "token_with_!@#$%^&*()"
    c.cookies.set("csrf_token", special_token)
    r = c.post("/post", headers={"X-CSRF-Token": special_token})
    assert r.status_code == 200


# Test different HTTP methods comprehensively
@pytest.mark.parametrize("method,endpoint", [
    ("GET", "/ping"),
    ("HEAD", "/head"),
    ("OPTIONS", "/options"),
    ("POST", "/post"),
    ("PUT", "/put"),
    ("PATCH", "/patch"),
    ("DELETE", "/delete"),
])
def test_csrf_all_methods_with_token(method, endpoint):
    """Test all HTTP methods with valid CSRF token."""
    c = TestClient(_app())
    t = "test_token"

    if method in ["GET", "HEAD", "OPTIONS"]:
        # These should always work regardless of token
        response = getattr(c, method.lower())(endpoint)
        assert response.status_code == 200
    else:
        # These require token
        c.cookies.set("csrf_token", t)
        response = getattr(c, method.lower())(endpoint, headers={"X-CSRF-Token": t})
        assert response.status_code == 200


@pytest.mark.parametrize("method,endpoint", [
    ("POST", "/post"),
    ("PUT", "/put"),
    ("PATCH", "/patch"),
    ("DELETE", "/delete"),
])
def test_csrf_all_methods_without_token(method, endpoint):
    """Test all HTTP methods without CSRF token (should fail for non-safe methods)."""
    c = TestClient(_app())

    response = getattr(c, method.lower())(endpoint)

    # Should fail for non-safe methods
    assert response.status_code in [400, 403]


