import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def mock_clerk_verify():
    """Mock Clerk token verification to return valid claims."""
    with patch('app.deps.clerk_auth.verify_clerk_token') as mock:
        mock.return_value = {
            "sub": "user_clerk_123",
            "user_id": "user_clerk_123",
            "email": "test@example.com"
        }
        yield mock


def test_whoami_with_clerk_cookie(mock_clerk_verify, monkeypatch):
    """Test that whoami endpoint recognizes Clerk session cookies."""
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    c = _client()
    
    # Test with Clerk session cookie
    r = c.get("/v1/whoami", cookies={"__session": "fake.clerk.token.here"})
    assert r.status_code == 200
    body = r.json()
    
    # Should be authenticated via Clerk
    assert body["is_authenticated"] is True
    assert body["session_ready"] is True
    assert body["source"] == "clerk"
    assert body["user"]["id"] == "user_clerk_123"
    assert body["user"]["email"] == "test@example.com"


def test_whoami_with_clerk_header(mock_clerk_verify, monkeypatch):
    """Test that whoami endpoint recognizes Clerk tokens in Authorization header."""
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    c = _client()
    
    # Test with Clerk token in Authorization header
    r = c.get("/v1/whoami", headers={"Authorization": "Bearer fake.clerk.token.here"})
    assert r.status_code == 200
    body = r.json()
    
    # Should be authenticated via Clerk
    assert body["is_authenticated"] is True
    assert body["session_ready"] is True
    assert body["source"] == "clerk"
    assert body["user"]["id"] == "user_clerk_123"


def test_whoami_with_invalid_clerk_token(monkeypatch):
    """Test that whoami endpoint handles invalid Clerk tokens gracefully."""
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    c = _client()
    
    # Mock Clerk verification to raise an exception
    with patch('app.deps.clerk_auth.verify_clerk_token') as mock:
        mock.side_effect = Exception("Invalid token")
        
        # Test with invalid Clerk token
        r = c.get("/v1/whoami", cookies={"__session": "invalid.clerk.token"})
        assert r.status_code == 200
        body = r.json()
        
        # Should not be authenticated
        assert body["is_authenticated"] is False
        assert body["session_ready"] is False
        assert body["source"] == "missing"


def test_whoami_fallback_to_clerk_when_jwt_fails(mock_clerk_verify, monkeypatch):
    """Test that whoami falls back to Clerk when traditional JWT fails."""
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    c = _client()
    
    # Test with both invalid JWT cookie and valid Clerk cookie
    r = c.get("/v1/whoami", cookies={
        "access_token": "invalid.jwt.token",
        "__session": "fake.clerk.token.here"
    })
    assert r.status_code == 200
    body = r.json()
    
    # Should be authenticated via Clerk fallback
    assert body["is_authenticated"] is True
    assert body["session_ready"] is True
    assert body["source"] == "clerk"
    assert body["user"]["id"] == "user_clerk_123"


def test_get_current_user_id_with_clerk(mock_clerk_verify, monkeypatch):
    """Test that get_current_user_id recognizes Clerk tokens."""
    # Set up environment to enable Clerk and disable traditional JWT
    monkeypatch.setenv("JWT_OPTIONAL_IN_TESTS", "1")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://test.clerk.accounts.dev/.well-known/jwks.json")
    monkeypatch.setenv("JWT_SECRET", "")  # No JWT secret so it won't try traditional JWT first
    
    from app.deps.user import get_current_user_id
    from fastapi import Request
    
    # Create a mock request with Clerk cookie - use a properly formatted JWT token
    mock_request = MagicMock(spec=Request)
    mock_request.method = "GET"
    mock_request.cookies = {"__session": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyX2NsZXJrXzEyMyIsInVzZXJfaWQiOiJ1c2VyX2NsZXJrXzEyMyIsImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSJ9.fake_signature"}
    mock_request.headers = {}
    
    # Mock the Clerk verification in the clerk_auth module
    with patch('app.deps.clerk_auth.verify_clerk_token') as mock:
        mock.return_value = {
            "sub": "user_clerk_123",
            "user_id": "user_clerk_123",
            "email": "test@example.com"
        }
        
        # Should return the Clerk user ID
        user_id = get_current_user_id(request=mock_request)
        assert user_id == "user_clerk_123"
