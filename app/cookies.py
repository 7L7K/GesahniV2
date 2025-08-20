"""
Cookie management facade module.

This module provides a clean interface for setting and clearing authentication cookies,
using the centralized cookie configuration for consistency.
"""

from typing import Optional
from fastapi import Response, Request

from .cookie_config import get_cookie_config, get_token_ttls, format_cookie_header


def set_auth_cookies(
    resp: Response, 
    access: str, 
    refresh: str, 
    session_id_or_none: Optional[str], 
    *, 
    access_ttl: int, 
    refresh_ttl: int
) -> None:
    """
    Set authentication cookies on the response.
    
    Args:
        resp: FastAPI Response object
        access: Access token string
        refresh: Refresh token string
        session_id_or_none: Optional session ID string
        access_ttl: Access token TTL in seconds
        refresh_ttl: Refresh token TTL in seconds
    """
    # Get cookie configuration from request context
    # Note: This requires the request to be available in the context
    # For now, we'll use a default configuration approach
    # TODO: In future steps, this will be refactored to accept a request parameter
    
    # For now, use environment-based configuration similar to cookie_config
    import os
    
    # Base configuration from environment
    cookie_secure = os.getenv("COOKIE_SECURE", "0").lower() in {"1", "true", "yes", "on"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    dev_mode = os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}
    
    # Development mode detection: force Secure=False for HTTP in dev
    if dev_mode:
        cookie_secure = False
    
    # SameSite=None requires Secure=True
    if cookie_samesite == "none":
        cookie_secure = True
    
    # Always use host-only cookies (no Domain) for better security
    domain = None
    
    cookie_config = {
        "secure": cookie_secure,
        "samesite": cookie_samesite,
        "httponly": True,
        "path": "/",
        "domain": domain,
    }
    
    # Set access token cookie
    access_header = format_cookie_header(
        key="access_token",
        value=access,
        max_age=access_ttl,
        secure=cookie_config["secure"],
        samesite=cookie_config["samesite"],
        path=cookie_config["path"],
        httponly=cookie_config["httponly"],
        domain=cookie_config["domain"],
    )
    resp.headers.append("Set-Cookie", access_header)
    
    # Set refresh token cookie
    refresh_header = format_cookie_header(
        key="refresh_token",
        value=refresh,
        max_age=refresh_ttl,
        secure=cookie_config["secure"],
        samesite=cookie_config["samesite"],
        path=cookie_config["path"],
        httponly=cookie_config["httponly"],
        domain=cookie_config["domain"],
    )
    resp.headers.append("Set-Cookie", refresh_header)
    
    # Set session cookie if provided
    if session_id_or_none:
        session_header = format_cookie_header(
            key="__session",
            value=session_id_or_none,
            max_age=access_ttl,
            secure=cookie_config["secure"],
            samesite=cookie_config["samesite"],
            path=cookie_config["path"],
            httponly=cookie_config["httponly"],
            domain=cookie_config["domain"],
        )
        resp.headers.append("Set-Cookie", session_header)


def clear_auth_cookies(resp: Response) -> None:
    """
    Clear all authentication cookies from the response.
    
    Args:
        resp: FastAPI Response object
    """
    # Use the same configuration approach as set_auth_cookies
    import os
    
    # Base configuration from environment
    cookie_secure = os.getenv("COOKIE_SECURE", "0").lower() in {"1", "true", "yes", "on"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    dev_mode = os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}
    
    # Development mode detection: force Secure=False for HTTP in dev
    if dev_mode:
        cookie_secure = False
    
    # SameSite=None requires Secure=True
    if cookie_samesite == "none":
        cookie_secure = True
    
    # Always use host-only cookies (no Domain) for better security
    domain = None
    
    cookie_config = {
        "secure": cookie_secure,
        "samesite": cookie_samesite,
        "httponly": True,
        "path": "/",
        "domain": domain,
    }
    
    # Clear all three cookies with identical attributes + Max-Age=0
    cookies_to_clear = ["access_token", "refresh_token", "__session"]
    
    for cookie_name in cookies_to_clear:
        # Set cookie with Max-Age=0 to clear it immediately
        header = format_cookie_header(
            key=cookie_name,
            value="",  # Empty value
            max_age=0,  # Max-Age=0 for immediate expiration
            secure=cookie_config["secure"],
            samesite=cookie_config["samesite"],
            path=cookie_config["path"],
            httponly=cookie_config["httponly"],
            domain=cookie_config["domain"]
        )
        resp.headers.append("Set-Cookie", header)
