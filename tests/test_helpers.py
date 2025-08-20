"""
Test helper utilities for authentication and cookie management.

This module provides centralized test utilities that align with the new auth facades
and invariants, ensuring consistent test patterns across the test suite.
"""

import os
import time
from typing import Optional, Dict, Any
from fastapi import Response, Request
from fastapi.testclient import TestClient

from app.cookies import set_auth_cookies, clear_auth_cookies
from app.tokens import create_access_token, create_refresh_token


def create_test_tokens(user_id: str, **kwargs) -> Dict[str, str]:
    """
    Create test access and refresh tokens for a user.
    
    Args:
        user_id: User ID for the tokens
        **kwargs: Additional claims to include in tokens
        
    Returns:
        Dictionary with 'access_token' and 'refresh_token' keys
    """
    claims = {"sub": user_id, **kwargs}
    return {
        "access_token": create_access_token(claims),
        "refresh_token": create_refresh_token(claims)
    }


def set_test_auth_cookies(
    client: TestClient,
    response: Response,
    user_id: str,
    session_id: Optional[str] = None,
    **token_kwargs
) -> None:
    """
    Set authentication cookies on a test response using the centralized facade.
    
    Args:
        client: TestClient instance for request context
        response: Response object to set cookies on
        user_id: User ID for token creation
        session_id: Optional session ID (if None, will be generated)
        **token_kwargs: Additional claims for tokens
    """
    # Create tokens
    tokens = create_test_tokens(user_id, **token_kwargs)
    
    # Create a mock request for cookie configuration
    # This is needed because set_auth_cookies requires request context
    mock_request = Request(scope={
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 8000)
    })
    
    # Get TTLs from environment or use defaults
    access_ttl = int(os.getenv("JWT_EXPIRE_MINUTES", "30")) * 60
    refresh_ttl = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440")) * 60
    
    # Set cookies using the centralized facade
    set_auth_cookies(
        resp=response,
        access=tokens["access_token"],
        refresh=tokens["refresh_token"],
        session_id=session_id,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=mock_request
    )


def clear_test_auth_cookies(client: TestClient, response: Response) -> None:
    """
    Clear authentication cookies from a test response using the centralized facade.
    
    Args:
        client: TestClient instance for request context
        response: Response object to clear cookies from
    """
    # Create a mock request for cookie configuration
    mock_request = Request(scope={
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 8000)
    })
    
    # Clear cookies using the centralized facade
    clear_auth_cookies(resp=response, request=mock_request)


def create_session_id() -> str:
    """
    Create a test session ID.
    
    Returns:
        A unique session ID string
    """
    return f"test_session_{int(time.time() * 1000)}"


def assert_cookies_present(response, expected_cookies=None):
    """
    Assert that expected cookies are present in the response.

    Args:
        response: Response object to check
        expected_cookies: List of expected cookie names (defaults to auth cookies)
    """
    if expected_cookies is None:
        expected_cookies = ["access_token", "refresh_token", "__session"]

    # Check both Set-Cookie headers and response.cookies
    set_cookie_header = response.headers.get("Set-Cookie", "")
    cookies = response.cookies
    
    # Debug output
    print(f"DEBUG: Set-Cookie header: {set_cookie_header}")
    print(f"DEBUG: Response cookies: {dict(cookies)}")
    
    for cookie_name in expected_cookies:
        # Check if cookie is in Set-Cookie header
        if cookie_name in set_cookie_header:
            continue
        # Check if cookie is in response.cookies
        if cookie_name in cookies:
            continue
        # If neither, fail
        assert False, f"Missing cookie: {cookie_name}"


def assert_cookies_cleared(response):
    """
    Assert that authentication cookies are cleared in the response.
    
    Args:
        response: Response object to check
    """
    set_cookie_header = response.headers.get("Set-Cookie", "")
    auth_cookies = ["access_token", "refresh_token", "__session"]
    
    for cookie_name in auth_cookies:
        assert cookie_name in set_cookie_header, f"Missing clear cookie: {cookie_name}"
        # Check that Max-Age=0 is present for clearing
        assert "Max-Age=0" in set_cookie_header, f"Cookie {cookie_name} not cleared with Max-Age=0"


def assert_session_opaque(response):
    """
    Assert that __session cookie has an opaque value (different from access_token).
    
    Args:
        response: Response object to check
    """
    # Get cookies from response
    cookies = response.cookies
    
    # Check that both cookies exist
    assert "access_token" in cookies, "access_token cookie not found"
    assert "__session" in cookies, "__session cookie not found"
    
    access_value = cookies["access_token"]
    session_value = cookies["__session"]
    
    # Session should be opaque (different from access token)
    assert session_value != access_value, "__session should have opaque value"
