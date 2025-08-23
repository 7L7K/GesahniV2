"""
Cookie management facade module.

This module provides a clean interface for setting and clearing authentication cookies,
using the centralized cookie configuration for consistency.

All Set-Cookie operations for auth and auth-adjacent flows go through this module.
No other module should call response.set_cookie() or append "Set-Cookie" headers directly.

Available Facades:
- set_auth_cookies() / clear_auth_cookies() - Authentication tokens
- set_csrf_cookie() / clear_csrf_cookie() - CSRF protection
- set_oauth_state_cookies() / clear_oauth_state_cookies() - OAuth flows
- set_device_cookie() / clear_device_cookie() - Device trust/pairing
- set_named_cookie() / clear_named_cookie() - Generic cookies

Usage:
    from app.cookies import set_auth_cookies, clear_auth_cookies
    
    # Set auth cookies
    set_auth_cookies(
        resp=response,
        access=access_token,
        refresh=refresh_token,
        session_id=session_id,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=request
    )
    
    # Clear auth cookies
    clear_auth_cookies(resp=response, request=request)
"""


from fastapi import Request, Response

from . import cookie_config as cookie_cfg
from .cookie_config import format_cookie_header, get_cookie_config
from .cookie_names import (
    ACCESS_TOKEN,
    ACCESS_TOKEN_LEGACY,
    REFRESH_TOKEN,
    REFRESH_TOKEN_LEGACY,
    SESSION,
    SESSION_LEGACY,
)


def set_auth_cookies(
    resp: Response,
    *,
    access: str,
    refresh: str,
    session_id: str | None = None,
    access_ttl: int,
    refresh_ttl: int,
    request: Request,
) -> None:
    """
    Set authentication cookies on the response.
    
    Sets access_token, refresh_token, and optionally __session cookies with
    consistent attributes from centralized configuration.
    
    Args:
        resp: FastAPI Response object
        access: Access token string
        refresh: Refresh token string
        session_id: Optional session ID string (must be opaque, never JWT)
        access_ttl: Access token TTL in seconds
        refresh_ttl: Refresh token TTL in seconds
        request: FastAPI Request object for cookie configuration
    
    Note:
        The __session cookie TTL is automatically aligned to the access token TTL
        to ensure consistent session lifecycle management. Call sites cannot override
        this alignment to prevent divergence.
    """
    # Get cookie configuration from request context
    cookie_config = cookie_cfg.get_cookie_config(request)
    
    # Set access token cookie (write canonical name)
    # Use the external-facing canonical name so clients see `access_token`.
    access_header = format_cookie_header(
        key=ACCESS_TOKEN,
        value=access,
        max_age=access_ttl,
        secure=cookie_config["secure"],
        samesite=cookie_config["samesite"],
        path=cookie_config["path"],
        httponly=cookie_config["httponly"],
        domain=cookie_config["domain"],
    )
    resp.headers.append("Set-Cookie", access_header)
    
    # Set refresh token cookie only if provided
    if refresh:
        refresh_header = format_cookie_header(
            key=REFRESH_TOKEN,
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
    # CRITICAL: __session TTL must always align with access token TTL
    # This prevents call sites from diverging and ensures consistent session lifecycle
    if session_id:
        # Use external-facing session cookie name (`__session`) for integrations
        session_header = format_cookie_header(
            key=SESSION,
            value=session_id,
            max_age=access_ttl,  # Always use access_ttl for session alignment
            secure=cookie_config["secure"],
            samesite=cookie_config["samesite"],
            path=cookie_config["path"],
            httponly=cookie_config["httponly"],
            domain=cookie_config["domain"],
        )
        resp.headers.append("Set-Cookie", session_header)

    # No legacy cookie clears — writes only touch canonical names


def clear_auth_cookies(resp: Response, request: Request) -> None:
    """
    Clear all authentication cookies from the response.
    
    Clears access_token, refresh_token, and __session cookies by setting
    Max-Age=0 with identical attributes to ensure proper deletion.
    
    Args:
        resp: FastAPI Response object
        request: FastAPI Request object for cookie configuration
    """
    # Get cookie configuration from request context
    cookie_config = cookie_cfg.get_cookie_config(request)
    
    # Clear both canonical external names and internal GSNH_* legacy names to
    # ensure interoperability during migrations and for clients using either.
    cookies_to_clear = [
        ACCESS_TOKEN,
        REFRESH_TOKEN,
        SESSION,
        ACCESS_TOKEN_LEGACY,
        REFRESH_TOKEN_LEGACY,
        SESSION_LEGACY,
    ]
    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for n in cookies_to_clear:
        if n not in seen:
            seen.add(n)
            deduped.append(n)
    for cookie_name in deduped:
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


def set_oauth_state_cookies(
    resp: Response, 
    *, 
    state: str, 
    next_url: str,
    request: Request,
    ttl: int = 600,  # Default 10 minutes
    provider: str = "oauth"  # Provider-specific cookie prefix
) -> None:
    """
    Set OAuth state cookies for Google/Apple OAuth flows.
    
    Sets both state and next_url cookies for CSRF protection and redirect handling.
    These cookies are separate from auth tokens and are cleared after OAuth callback.
    
    Args:
        resp: FastAPI Response object
        state: OAuth state parameter for CSRF protection
        next_url: URL to redirect to after OAuth completion
        request: FastAPI Request object for cookie configuration
        ttl: Time to live in seconds (default: 600 = 10 minutes)
        provider: Provider prefix for cookie names (e.g., "g" for Google, "oauth" for Apple)
    """
    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)
    
    # Set OAuth state cookie (HttpOnly for security)
    state_cookie_name = f"{provider}_state"
    state_header = format_cookie_header(
        key=state_cookie_name,
        value=state,
        max_age=ttl,
        secure=cookie_config["secure"],
        samesite=cookie_config["samesite"],
        path=cookie_config["path"],
        httponly=True,  # State should be HttpOnly for security
        domain=cookie_config["domain"],
    )
    resp.headers.append("Set-Cookie", state_header)
    
    # Set OAuth next URL cookie (not HttpOnly so client can read it)
    next_cookie_name = f"{provider}_next"
    next_header = format_cookie_header(
        key=next_cookie_name,
        value=next_url,
        max_age=ttl,
        secure=cookie_config["secure"],
        samesite=cookie_config["samesite"],
        path=cookie_config["path"],
        httponly=False,  # Next URL needs to be accessible to client
        domain=cookie_config["domain"],
    )
    resp.headers.append("Set-Cookie", next_header)


def clear_oauth_state_cookies(resp: Response, request: Request, provider: str = "oauth") -> None:
    """
    Clear OAuth state cookies from the response.
    
    Args:
        resp: FastAPI Response object
        request: FastAPI Request object for cookie configuration
        provider: Provider prefix for cookie names (e.g., "g" for Google, "oauth" for Apple)
    """
    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)
    
    # Clear OAuth state cookies with Max-Age=0
    state_cookie_name = f"{provider}_state"
    next_cookie_name = f"{provider}_next"
    oauth_cookies = [state_cookie_name, next_cookie_name]
    
    for cookie_name in oauth_cookies:
        header = format_cookie_header(
            key=cookie_name,
            value="",  # Empty value
            max_age=0,  # Max-Age=0 for immediate expiration
            secure=cookie_config["secure"],
            samesite=cookie_config["samesite"],
            path=cookie_config["path"],
            httponly=cookie_name == state_cookie_name,  # State is HttpOnly, next is not
            domain=cookie_config["domain"]
        )
        resp.headers.append("Set-Cookie", header)


def set_csrf_cookie(
    resp: Response, 
    *, 
    token: str, 
    ttl: int,
    request: Request
) -> None:
    """
    Set CSRF token cookie for double-submit protection.
    
    Args:
        resp: FastAPI Response object
        token: CSRF token string
        ttl: Time to live in seconds
        request: FastAPI Request object for cookie configuration
    """
    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)
    
    # CSRF cookies need special handling for cross-site scenarios
    csrf_samesite = cookie_config["samesite"]
    if csrf_samesite == "none":
        # Ensure Secure=True when SameSite=None
        csrf_secure = True
    else:
        # For same-origin scenarios, use standard configuration
        csrf_secure = cookie_config["secure"]
    
    # Set CSRF token cookie (not HttpOnly so client can echo it back)
    csrf_header = format_cookie_header(
        key="csrf_token",
        value=token,
        max_age=ttl,
        secure=csrf_secure,
        samesite=csrf_samesite,
        path=cookie_config["path"],
        httponly=False,  # CSRF tokens need to be accessible to JavaScript
        domain=cookie_config["domain"],
    )
    resp.headers.append("Set-Cookie", csrf_header)


def clear_csrf_cookie(resp: Response, request: Request) -> None:
    """
    Clear CSRF token cookie from the response.
    
    Args:
        resp: FastAPI Response object
        request: FastAPI Request object for cookie configuration
    """
    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)
    
    # CSRF cookies need special handling for cross-site scenarios
    csrf_samesite = cookie_config["samesite"]
    if csrf_samesite == "none":
        # Ensure Secure=True when SameSite=None
        csrf_secure = True
    else:
        # For same-origin scenarios, use standard configuration
        csrf_secure = cookie_config["secure"]
    
    # Clear CSRF token cookie with Max-Age=0
    csrf_header = format_cookie_header(
        key="csrf_token",
        value="",  # Empty value
        max_age=0,  # Max-Age=0 for immediate expiration
        secure=csrf_secure,
        samesite=csrf_samesite,
        path=cookie_config["path"],
        httponly=False,  # CSRF tokens need to be accessible to JavaScript
        domain=cookie_config["domain"]
    )
    resp.headers.append("Set-Cookie", csrf_header)


def set_device_cookie(
    resp: Response, 
    *, 
    value: str, 
    ttl: int,
    request: Request,
    cookie_name: str = "device_trust"
) -> None:
    """
    Set device trust/pairing cookie.
    
    Args:
        resp: FastAPI Response object
        value: Device trust value string
        ttl: Time to live in seconds
        request: FastAPI Request object for cookie configuration
        cookie_name: Name of the device cookie (default: "device_trust")
    """
    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)
    
    # Device cookies are not HttpOnly so client can access them
    device_header = format_cookie_header(
        key=cookie_name,
        value=value,
        max_age=ttl,
        secure=cookie_config["secure"],
        samesite=cookie_config["samesite"],
        path=cookie_config["path"],
        httponly=False,  # Device cookies need to be accessible to JavaScript
        domain=cookie_config["domain"],
    )
    resp.headers.append("Set-Cookie", device_header)


def clear_device_cookie(
    resp: Response, 
    request: Request, 
    cookie_name: str = "device_trust"
) -> None:
    """
    Clear device trust/pairing cookie from the response.
    
    Args:
        resp: FastAPI Response object
        request: FastAPI Request object for cookie configuration
        cookie_name: Name of the device cookie to clear (default: "device_trust")
    """
    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)
    
    # Clear device cookie with Max-Age=0
    device_header = format_cookie_header(
        key=cookie_name,
        value="",  # Empty value
        max_age=0,  # Max-Age=0 for immediate expiration
        secure=cookie_config["secure"],
        samesite=cookie_config["samesite"],
        path=cookie_config["path"],
        httponly=False,  # Device cookies need to be accessible to JavaScript
        domain=cookie_config["domain"]
    )
    resp.headers.append("Set-Cookie", device_header)


def set_named_cookie(
    resp: Response,
    *,
    name: str,
    value: str,
    ttl: int,
    request: Request,
    httponly: bool = True,
    path: str = None,
    domain: str = None,
    secure: bool = None,
    samesite: str = None
) -> None:
    """
    Set a generic named cookie with centralized configuration.
    
    This function provides a generic interface for setting any cookie that doesn't
    fit the specific auth/OAuth/CSRF patterns. It uses centralized configuration
    but allows override of specific attributes when needed.
    
    Args:
        resp: FastAPI Response object
        name: Cookie name
        value: Cookie value
        ttl: Time to live in seconds
        request: FastAPI Request object for cookie configuration
        httponly: Whether cookie is HttpOnly (default: True)
        path: Cookie path (default: from config)
        domain: Cookie domain (default: from config)
        secure: Whether cookie is secure (default: from config)
        samesite: SameSite attribute (default: from config)
    """
    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)
    
    # Use provided values or fall back to config defaults
    cookie_path = path or cookie_config["path"]
    cookie_domain = domain if domain is not None else cookie_config["domain"]
    cookie_secure = secure if secure is not None else cookie_config["secure"]
    cookie_samesite = samesite or cookie_config["samesite"]
    
    # Format the cookie header
    header = format_cookie_header(
        key=name,
        value=value,
        max_age=ttl,
        secure=cookie_secure,
        samesite=cookie_samesite,
        path=cookie_path,
        httponly=httponly,
        domain=cookie_domain,
    )
    resp.headers.append("Set-Cookie", header)


def clear_named_cookie(
    resp: Response,
    *,
    name: str,
    request: Request,
    path: str = None,
    domain: str = None,
    secure: bool = None,
    samesite: str = None
) -> None:
    """
    Clear a generic named cookie with centralized configuration.
    
    Args:
        resp: FastAPI Response object
        name: Cookie name to clear
        request: FastAPI Request object for cookie configuration
        path: Cookie path (default: from config)
        domain: Cookie domain (default: from config)
        secure: Whether cookie is secure (default: from config)
        samesite: SameSite attribute (default: from config)
    """
    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)
    
    # Use provided values or fall back to config defaults
    cookie_path = path or cookie_config["path"]
    cookie_domain = domain if domain is not None else cookie_config["domain"]
    cookie_secure = secure if secure is not None else cookie_config["secure"]
    cookie_samesite = samesite or cookie_config["samesite"]
    
    # Clear cookie with Max-Age=0
    header = format_cookie_header(
        key=name,
        value="",  # Empty value
        max_age=0,  # Max-Age=0 for immediate expiration
        secure=cookie_secure,
        samesite=cookie_samesite,
        path=cookie_path,
        httponly=True,  # Default to HttpOnly for security
        domain=cookie_domain
    )
    resp.headers.append("Set-Cookie", header)


def _set_cookie(resp: Response, name: str, value: str, *, request: Request, ttl: int | None,
                http_only: bool, same_site: str | None = None) -> None:
    """Base cookie setter with centralized configuration."""
    cookie_config = get_cookie_config(request)
    resp.set_cookie(
        key=name,
        value=value,
        max_age=ttl,
        secure=cookie_config["secure"],
        samesite=same_site or cookie_config["samesite"],  # 'Lax' or 'None'; prod https => None if cross-site
        httponly=http_only,
        path=cookie_config["path"],
        domain=cookie_config["domain"],  # may be None in dev
    )

def set_session_cookie(resp: Response, token: str, *, request: Request, ttl: int) -> None:
    """Set HttpOnly session cookie."""
    _set_cookie(resp, "session", token, request=request, ttl=ttl, http_only=True)

def set_refresh_cookie(resp: Response, token: str, *, request: Request, ttl: int) -> None:
    """Set HttpOnly refresh token cookie."""
    _set_cookie(resp, "refresh", token, request=request, ttl=ttl, http_only=True)

def set_csrf_cookie(resp: Response, token: str, *, request: Request, ttl: int) -> None:
    """Set CSRF cookie (intentionally NOT HttpOnly for double-submit pattern)."""
    _set_cookie(resp, "csrf", token, request=request, ttl=ttl, http_only=False)

def set_oauth_state_cookie(resp: Response, token: str, *, request: Request, ttl: int = 600) -> None:
    """Set OAuth state cookie with Lax SameSite for security."""
    _set_cookie(resp, "oauth_state", token, request=request, ttl=ttl, http_only=True, same_site="Lax")

def get_cookie(request: Request, name: str) -> str | None:
    """Plain cookie reader — no legacy fallbacks.

    Use direct `get_cookie(request, GSNH_AT)` for auth reads to ensure only canonical
    names are relied upon.
    """
    return request.cookies.get(name)


# Export all cookie facade functions
__all__ = [
    "set_auth_cookies",
    "clear_auth_cookies",
    "set_oauth_state_cookies",
    "clear_oauth_state_cookies",
    "set_csrf_cookie",
    "clear_csrf_cookie",
    "set_device_cookie",
    "clear_device_cookie",
    "set_named_cookie",
    "clear_named_cookie",
    "_set_cookie",
    "set_session_cookie",
    "set_refresh_cookie",
    "set_oauth_state_cookie",
]
