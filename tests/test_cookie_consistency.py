"""
Tests for cookie consistency and duplicate cookie prevention.

This test file verifies that:
1. Login endpoint doesn't set duplicate cookies
2. Cookies are set with consistent attributes
3. Logout properly revokes tokens and clears cookies
"""

import tempfile
import os
import sys
from importlib import import_module
from fastapi.testclient import TestClient
from fastapi import FastAPI, Request
from jose import jwt

from app.deps.user import get_current_user_id


def _client(monkeypatch):
    """Create a test client with temporary database."""
    db_fd, db_path = tempfile.mkstemp()
    os.close(db_fd)
    monkeypatch.setenv("USERS_DB", db_path)
    monkeypatch.setenv("JWT_SECRET", "testsecret")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "5")
    monkeypatch.setenv("JWT_REFRESH_EXPIRE_MINUTES", "1440")
    monkeypatch.setenv("PYTEST_RUNNING", "1")  # Add this to match the original test
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")  # Use memory backend for tests
    monkeypatch.setenv("DEV_MODE", "1")  # Enable dev mode for testing
    sys.modules.pop("app.auth", None)
    auth = import_module("app.auth")
    app = FastAPI()
    app.include_router(auth.router)
    client = TestClient(app)
    
    # Override the user dependency like in the original test
    def fake_user_id(request: Request) -> str:
        request.state.user_id = "abc"
        return "abc"
    client.app.dependency_overrides[get_current_user_id] = fake_user_id
    
    client.post("/register", json={"username": "alice", "password": "wonderland"})
    return client


def test_login_sets_cookies_once(monkeypatch):
    """Test that login endpoint sets cookies only once (no duplicates)."""
    client = _client(monkeypatch)
    
    # Login and capture response
    resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert resp.status_code == 200
    
    # Check that Set-Cookie headers are present
    set_cookie_header = resp.headers.get("set-cookie")
    assert set_cookie_header is not None
    
    # Split multiple cookies if present
    set_cookie_headers = [h.strip() for h in set_cookie_header.split(",") if h.strip()]
    assert len(set_cookie_headers) > 0
    
    # Check for access_token, refresh_token, and __session cookies
    access_cookies = [h for h in set_cookie_headers if "access_token=" in h]
    refresh_cookies = [h for h in set_cookie_headers if "refresh_token=" in h]
    session_cookies = [h for h in set_cookie_headers if "__session=" in h]
    
    # Should have exactly one of each
    assert len(access_cookies) == 1, f"Expected 1 access_token cookie, got {len(access_cookies)}"
    assert len(refresh_cookies) == 1, f"Expected 1 refresh_token cookie, got {len(refresh_cookies)}"
    assert len(session_cookies) == 1, f"Expected 1 __session cookie, got {len(session_cookies)}"
    
    # Verify cookie attributes are consistent
    access_cookie = access_cookies[0]
    refresh_cookie = refresh_cookies[0]
    session_cookie = session_cookies[0]
    
    # Check for required attributes
    assert "HttpOnly" in access_cookie
    assert "HttpOnly" in refresh_cookie
    assert "HttpOnly" in session_cookie
    assert "Path=/" in access_cookie
    assert "Path=/" in refresh_cookie
    assert "Path=/" in session_cookie
    assert "SameSite=Lax" in access_cookie
    assert "SameSite=Lax" in refresh_cookie
    assert "SameSite=Lax" in session_cookie
    
    # Check that __session has same value as access_token
    access_value = access_cookie.split(";")[0].split("=", 1)[1]
    session_value = session_cookie.split(";")[0].split("=", 1)[1]
    assert access_value == session_value


def test_refresh_sets_cookies_once(monkeypatch):
    """Test that refresh endpoint sets cookies only once (no duplicates)."""
    client = _client(monkeypatch)
    
    # Login first
    login_resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    
    # Refresh and capture response
    refresh_resp = client.post("/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_resp.status_code == 200
    
    # Check that Set-Cookie headers are present
    set_cookie_header = refresh_resp.headers.get("set-cookie")
    assert set_cookie_header is not None
    
    # Split multiple cookies if present
    set_cookie_headers = [h.strip() for h in set_cookie_header.split(",") if h.strip()]
    assert len(set_cookie_headers) > 0
    
    # Check for access_token, refresh_token, and __session cookies
    access_cookies = [h for h in set_cookie_headers if "access_token=" in h]
    refresh_cookies = [h for h in set_cookie_headers if "refresh_token=" in h]
    session_cookies = [h for h in set_cookie_headers if "__session=" in h]
    
    # Should have exactly one of each
    assert len(access_cookies) == 1, f"Expected 1 access_token cookie, got {len(access_cookies)}"
    assert len(refresh_cookies) == 1, f"Expected 1 refresh_token cookie, got {len(refresh_cookies)}"
    assert len(session_cookies) == 1, f"Expected 1 __session cookie, got {len(session_cookies)}"
    
    # Verify cookie attributes are consistent
    access_cookie = access_cookies[0]
    refresh_cookie = refresh_cookies[0]
    session_cookie = session_cookies[0]
    
    # Check for required attributes
    assert "HttpOnly" in access_cookie
    assert "HttpOnly" in refresh_cookie
    assert "HttpOnly" in session_cookie
    assert "Path=/" in access_cookie
    assert "Path=/" in refresh_cookie
    assert "Path=/" in session_cookie
    assert "SameSite=Lax" in access_cookie
    assert "SameSite=Lax" in refresh_cookie
    assert "SameSite=Lax" in session_cookie
    
    # Check that __session has same value as access_token
    access_value = access_cookie.split(";")[0].split("=", 1)[1]
    session_value = session_cookie.split(";")[0].split("=", 1)[1]
    assert access_value == session_value


def test_logout_clears_cookies_properly(monkeypatch):
    """Test that logout properly clears cookies and revokes tokens."""
    client = _client(monkeypatch)
    
    # Login first
    login_resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    
    # Refresh to get new tokens
    refresh_resp = client.post("/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh_resp.status_code == 200
    new_tokens = refresh_resp.json()
    
    # Logout with the latest refresh token
    logout_resp = client.post("/logout", headers={"Authorization": f"Bearer {new_tokens['refresh_token']}"})
    assert logout_resp.status_code == 204
    
    # Check that Set-Cookie headers are present for clearing
    set_cookie_header = logout_resp.headers.get("set-cookie")
    assert set_cookie_header is not None
    
    # Split multiple cookies if present
    set_cookie_headers = [h.strip() for h in set_cookie_header.split(",") if h.strip()]
    assert len(set_cookie_headers) > 0
    
    # Check for cleared access_token, refresh_token, and __session cookies
    access_cookies = [h for h in set_cookie_headers if "access_token=" in h]
    refresh_cookies = [h for h in set_cookie_headers if "refresh_token=" in h]
    session_cookies = [h for h in set_cookie_headers if "__session=" in h]
    
    # Should have exactly one of each for clearing
    assert len(access_cookies) == 1, f"Expected 1 access_token clear cookie, got {len(access_cookies)}"
    assert len(refresh_cookies) == 1, f"Expected 1 refresh_token clear cookie, got {len(refresh_cookies)}"
    assert len(session_cookies) == 1, f"Expected 1 __session clear cookie, got {len(session_cookies)}"
    
    # Verify cookies are cleared (empty value and expired)
    access_cookie = access_cookies[0]
    refresh_cookie = refresh_cookies[0]
    session_cookie = session_cookies[0]
    
    assert "access_token=;" in access_cookie or "access_token= " in access_cookie
    assert "refresh_token=;" in refresh_cookie or "refresh_token= " in refresh_cookie
    assert "__session=;" in session_cookie or "__session= " in session_cookie
    assert "Max-Age=0" in access_cookie
    assert "Max-Age=0" in refresh_cookie
    assert "Max-Age=0" in session_cookie
    
    # Verify that the refresh token is no longer valid
    invalid_refresh_resp = client.post("/refresh", json={"refresh_token": new_tokens["refresh_token"]})
    assert invalid_refresh_resp.status_code == 401


def test_cookie_attributes_consistency(monkeypatch):
    """Test that all cookies have consistent attributes across endpoints."""
    client = _client(monkeypatch)
    
    # Login
    login_resp = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert login_resp.status_code == 200
    
    # Get cookies from login
    login_cookie_header = login_resp.headers.get("set-cookie")
    assert login_cookie_header is not None
    login_cookies = [h.strip() for h in login_cookie_header.split(",") if h.strip()]
    login_access = [h for h in login_cookies if "access_token=" in h][0]
    login_refresh = [h for h in login_cookies if "refresh_token=" in h][0]
    login_session = [h for h in login_cookies if "__session=" in h][0]
    
    # Verify consistent attributes for login cookies
    for attr in ["HttpOnly", "Path=/", "SameSite=Lax"]:
        assert attr in login_access
        assert attr in login_refresh
        assert attr in login_session
    
    # Verify Priority=High for auth cookies
    assert "Priority=High" in login_access
    assert "Priority=High" in login_refresh
    assert "Priority=High" in login_session
