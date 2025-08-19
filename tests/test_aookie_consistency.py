import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import jwt
import time
from datetime import datetime, timedelta

from app.main import app
from app.auth import SECRET_KEY, ALGORITHM


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_user_store():
    with patch('app.auth.user_store') as mock:
        mock.ensure_user.return_value = None
        mock.increment_login.return_value = None
        mock.get_stats.return_value = {}
        yield mock


def test_login_sets_all_three_cookies_consistently(client, mock_user_store):
    """Test that login endpoint sets all three cookies consistently."""
    response = client.post("/login", json={"username": "alice", "password": "wonderland"})
    
    assert response.status_code == 200
    
    # Check that all three cookies are set
    cookies = response.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies
    assert "__session" in cookies
    
    # Verify all cookies have consistent attributes
    access_cookie = cookies["access_token"]
    refresh_cookie = cookies["refresh_token"]
    session_cookie = cookies["__session"]
    
    # Check that __session has same value as access_token
    assert session_cookie.value == access_cookie.value
    
    # Check that all cookies have same secure and samesite attributes
    assert access_cookie.secure == refresh_cookie.secure == session_cookie.secure
    assert access_cookie.samesite == refresh_cookie.samesite == session_cookie.samesite
    assert access_cookie.path == refresh_cookie.path == session_cookie.path == "/"
    assert access_cookie.httponly == refresh_cookie.httponly == session_cookie.httponly == True
    
    # Check that access_token and __session have same max_age
    assert access_cookie.max_age == session_cookie.max_age
    # refresh_token should have longer max_age
    assert refresh_cookie.max_age > access_cookie.max_age


def test_refresh_rotates_all_three_cookies_consistently(client, mock_user_store):
    """Test that refresh endpoint rotates all three cookies consistently."""
    # First login to get initial tokens
    login_response = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert login_response.status_code == 200
    
    # Get refresh token from login response
    refresh_token = login_response.json()["refresh_token"]
    
    # Use refresh token to get new tokens
    refresh_response = client.post("/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 200
    
    # Check that all three cookies are set in refresh response
    cookies = refresh_response.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies
    assert "__session" in cookies
    
    # Verify all cookies have consistent attributes
    access_cookie = cookies["access_token"]
    refresh_cookie = cookies["refresh_token"]
    session_cookie = cookies["__session"]
    
    # Check that __session has same value as access_token
    assert session_cookie.value == access_cookie.value
    
    # Check that all cookies have same secure and samesite attributes
    assert access_cookie.secure == refresh_cookie.secure == session_cookie.secure
    assert access_cookie.samesite == refresh_cookie.samesite == session_cookie.samesite
    assert access_cookie.path == refresh_cookie.path == session_cookie.path == "/"
    assert access_cookie.httponly == refresh_cookie.httponly == session_cookie.httponly == True
    
    # Check that access_token and __session have same max_age
    assert access_cookie.max_age == session_cookie.max_age
    # refresh_token should have longer max_age
    assert refresh_cookie.max_age > access_cookie.max_age
    
    # Verify that tokens are different from original login (rotation occurred)
    original_access = login_response.cookies["access_token"].value
    new_access = access_cookie.value
    assert original_access != new_access


def test_logout_clears_all_three_cookies_consistently(client, mock_user_store):
    """Test that logout endpoint clears all three cookies consistently."""
    # First login to get tokens
    login_response = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert login_response.status_code == 200
    
    # Get access token for logout
    access_token = login_response.json()["access_token"]
    
    # Logout
    logout_response = client.post("/logout", headers={"Authorization": f"Bearer {access_token}"})
    assert logout_response.status_code == 204
    
    # Check that all three cookies are cleared
    cookies = logout_response.cookies
    assert "access_token" in cookies
    assert "refresh_token" in cookies
    assert "__session" in cookies
    
    # Verify all cookies are cleared (empty value and max_age=0)
    for cookie_name in ["access_token", "refresh_token", "__session"]:
        cookie = cookies[cookie_name]
        assert cookie.value == ""
        assert cookie.max_age == 0
    
    # Check that all cookies have consistent attributes
    access_cookie = cookies["access_token"]
    refresh_cookie = cookies["refresh_token"]
    session_cookie = cookies["__session"]
    
    assert access_cookie.secure == refresh_cookie.secure == session_cookie.secure
    assert access_cookie.samesite == refresh_cookie.samesite == session_cookie.samesite
    assert access_cookie.path == refresh_cookie.path == session_cookie.path == "/"
    assert access_cookie.httponly == refresh_cookie.httponly == session_cookie.httponly == True


def test_oauth_callback_sets_all_three_cookies_consistently(client):
    """Test that OAuth callback endpoints set all three cookies consistently."""
    # Mock OAuth flow for Google callback
    with patch('app.api.oauth_google.exchange_code') as mock_exchange, \
         patch('httpx.AsyncClient') as mock_client:
        
        # Mock successful OAuth exchange
        mock_creds = MagicMock()
        mock_creds.token = "mock_google_token"
        mock_creds.refresh_token = "mock_refresh_token"
        mock_exchange.return_value = mock_creds
        
        # Mock userinfo response
        mock_userinfo = {"email": "test@example.com", "sub": "12345"}
        mock_client_instance = MagicMock()
        mock_client_instance.__aenter__.return_value.post.return_value.status_code = 200
        mock_client_instance.__aenter__.return_value.post.return_value.json.return_value = {"id_token": "mock_id_token"}
        mock_client_instance.__aenter__.return_value.get.return_value.status_code = 200
        mock_client_instance.__aenter__.return_value.get.return_value.json.return_value = mock_userinfo
        mock_client.return_value = mock_client_instance
        
        # Mock session creation
        with patch('app.api.oauth_google.sessions_store') as mock_sessions:
            mock_sessions.create_session.return_value = {"sid": "test_sid", "did": "test_did"}
            
            # Call OAuth callback
            response = client.get("/auth/google/callback?code=test_code&state=test_state")
            
            # Should redirect with cookies set
            assert response.status_code == 302
            
            # Check that all three cookies are set
            cookies = response.cookies
            assert "access_token" in cookies
            assert "refresh_token" in cookies
            assert "__session" in cookies
            
            # Verify all cookies have consistent attributes
            access_cookie = cookies["access_token"]
            refresh_cookie = cookies["refresh_token"]
            session_cookie = cookies["__session"]
            
            # Check that __session has same value as access_token
            assert session_cookie.value == access_cookie.value
            
            # Check that all cookies have same secure and samesite attributes
            assert access_cookie.secure == refresh_cookie.secure == session_cookie.secure
            assert access_cookie.samesite == refresh_cookie.samesite == session_cookie.samesite
            assert access_cookie.path == refresh_cookie.path == session_cookie.path == "/"
            assert access_cookie.httponly == refresh_cookie.httponly == session_cookie.httponly == True
            
            # Check that access_token and __session have same max_age
            assert access_cookie.max_age == session_cookie.max_age
            # refresh_token should have longer max_age
            assert refresh_cookie.max_age > access_cookie.max_age


def test_finish_clerk_login_sets_all_three_cookies_consistently(client):
    """Test that Clerk finish endpoint sets all three cookies consistently."""
    with patch('app.api.auth._require_user_or_dev') as mock_require_user:
        mock_require_user.return_value = "test_user"
        
        # Call finish endpoint
        response = client.post("/auth/finish")
        
        assert response.status_code == 204
        
        # Check that all three cookies are set
        cookies = response.cookies
        assert "access_token" in cookies
        assert "refresh_token" in cookies
        assert "__session" in cookies
        
        # Verify all cookies have consistent attributes
        access_cookie = cookies["access_token"]
        refresh_cookie = cookies["refresh_token"]
        session_cookie = cookies["__session"]
        
        # Check that __session has same value as access_token
        assert session_cookie.value == access_cookie.value
        
        # Check that all cookies have same secure and samesite attributes
        assert access_cookie.secure == refresh_cookie.secure == session_cookie.secure
        assert access_cookie.samesite == refresh_cookie.samesite == session_cookie.samesite
        assert access_cookie.path == refresh_cookie.path == session_cookie.path == "/"
        assert access_cookie.httponly == refresh_cookie.httponly == session_cookie.httponly == True
        
        # Check that access_token and __session have same max_age
        assert access_cookie.max_age == session_cookie.max_age
        # refresh_token should have longer max_age
        assert refresh_cookie.max_age > access_cookie.max_age


def test_cookie_attributes_consistency_across_endpoints(client, mock_user_store):
    """Test that cookie attributes are consistent across all endpoints."""
    # Test login endpoint
    login_response = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert login_response.status_code == 200
    
    login_cookies = login_response.cookies
    login_secure = login_cookies["access_token"].secure
    login_samesite = login_cookies["access_token"].samesite
    
    # Test refresh endpoint
    refresh_token = login_response.json()["refresh_token"]
    refresh_response = client.post("/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 200
    
    refresh_cookies = refresh_response.cookies
    refresh_secure = refresh_cookies["access_token"].secure
    refresh_samesite = refresh_cookies["access_token"].samesite
    
    # Test logout endpoint
    access_token = login_response.json()["access_token"]
    logout_response = client.post("/logout", headers={"Authorization": f"Bearer {access_token}"})
    assert logout_response.status_code == 204
    
    logout_cookies = logout_response.cookies
    logout_secure = logout_cookies["access_token"].secure
    logout_samesite = logout_cookies["access_token"].samesite
    
    # Verify consistent attributes across all endpoints
    assert login_secure == refresh_secure == logout_secure
    assert login_samesite == refresh_samesite == logout_samesite


def test_session_cookie_matches_access_token(client, mock_user_store):
    """Test that __session cookie always matches access_token value."""
    # Test login
    login_response = client.post("/login", json={"username": "alice", "password": "wonderland"})
    assert login_response.status_code == 200
    
    login_cookies = login_response.cookies
    assert login_cookies["__session"].value == login_cookies["access_token"].value
    
    # Test refresh
    refresh_token = login_response.json()["refresh_token"]
    refresh_response = client.post("/refresh", json={"refresh_token": refresh_token})
    assert refresh_response.status_code == 200
    
    refresh_cookies = refresh_response.cookies
    assert refresh_cookies["__session"].value == refresh_cookies["access_token"].value
    
    # Verify that session cookie was updated to new access token
    assert login_cookies["access_token"].value != refresh_cookies["access_token"].value
    assert login_cookies["__session"].value != refresh_cookies["__session"].value
