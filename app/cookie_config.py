"""
Centralized cookie configuration for sharp and consistent cookie handling.

This module provides a single source of truth for cookie configuration,
ensuring all cookies are set with consistent attributes:
- Host-only cookies (no Domain)
- Path=/
- SameSite=Lax (configurable)
- HttpOnly=True
- Secure=False in dev HTTP, True in production
- Consistent TTLs for access/refresh tokens

Environment Variables:
- COOKIE_SECURE: Force secure cookies (default: auto-detect)
- COOKIE_SAMESITE: SameSite attribute (default: "lax")
- JWT_EXPIRE_MINUTES: Access token TTL (default: 15)
- JWT_REFRESH_EXPIRE_MINUTES: Refresh token TTL (default: 43200)
- DEV_MODE: Development mode flag (default: auto-detect)
"""

import os
from typing import Any

from fastapi import Request


def get_cookie_config(request: Request) -> dict[str, Any]:
    """
    Get consistent cookie configuration for the current request.

    Computes secure, samesite, domain, path, max_age from environment variables
    and request context. This is the single source of truth for all cookie attributes.

    Args:
        request: FastAPI Request object for context detection

    Returns:
        dict: Cookie configuration with secure, samesite, httponly, path, domain
    """
    # Base configuration from environment
    # Determine secure flag: check if explicitly forced
    env_secure = os.getenv("COOKIE_SECURE", "").strip().lower()
    env_force_secure = env_secure in {"1", "true", "yes", "on"}
    env_force_insecure = env_secure in {"0", "false", "no", "off"}

    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    # Consider USE_DEV_PROXY an explicit signal that we're running local dev
    dev_mode = os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"} or os.getenv("USE_DEV_PROXY", "0").lower() in {"1", "true", "yes", "on"}

    # Development mode detection: on dev + non-HTTPS, ensure cookies are
    # localhost-safe: Secure=False, SameSite=Lax, host-only (no Domain).
    dev_env_detected = dev_mode or _is_dev_environment(request)
    is_tls = _get_scheme(request) == "https"

    # Determine secure flag with HTTPS taking precedence. Order of precedence:
    # 1) COOKIE_SECURE=1 (force secure)
    # 2) If request is TLS (HTTPS) -> secure
    # 3) COOKIE_SECURE=0 (force insecure)
    # 4) default to False
    if env_force_secure:
        cookie_secure = True
    elif is_tls:
        cookie_secure = True
    elif env_force_insecure:
        cookie_secure = False
    else:
        cookie_secure = False

    # If in dev or on localhost over plain HTTP, ensure cookies are accepted by browsers
    if dev_env_detected and not is_tls:
        # In dev mode over HTTP, always force Secure=False for localhost compatibility
        # This overrides any COOKIE_SECURE setting to ensure cookies work in development
        cookie_secure = False

    # Enforce that when SameSite=None is requested, Secure must be True per RFC.
    # Tests may request SameSite=None and expect Secure to be present; ensure
    # we add the Secure attribute even if other logic would disable it.
    if cookie_samesite == "none":
        cookie_secure = True

    # SameSite=None requires Secure=True. If SameSite=None is requested but secure is not
    # set, force secure=True to avoid creating invalid cookie combinations.
    if cookie_samesite == "none":
        cookie_secure = True

    # Always use host-only cookies (no Domain) for better security and Safari compatibility
    # Ports don't matter for cookies; Domain does. Host-only is the least-surprising choice.
    domain = None

    # In production, allow setting a top-level domain for cookies so subservices
    # (backend vs frontend) share the same site cookie. Respect APP_DOMAIN env var.
    app_domain = os.getenv("APP_DOMAIN")
    if not dev_env_detected and app_domain:
        domain = app_domain
        # Ensure production cookies are secure and SameSite=Lax by default
        cookie_secure = True
        cookie_samesite = "lax"

    return {
        "secure": cookie_secure,
        "samesite": cookie_samesite,
        "httponly": True,
        "path": "/",
        "domain": domain,
    }


def _is_dev_environment(request: Request) -> bool:
    """Detect if we're in a development environment."""
    # Check for common dev indicators
    dev_indicators = [
        os.getenv("PYTEST_CURRENT_TEST"),  # Running tests
        os.getenv("FLASK_ENV") == "development",
        os.getenv("ENVIRONMENT") == "development",
        os.getenv("NODE_ENV") == "development",
    ]

    if any(dev_indicators):
        return True

    # Check request host for localhost/dev patterns
    try:
        host = request.headers.get("host", "").lower()
        dev_hosts = ["localhost", "0.0.0.0", "127.0.0.1", "::1", "dev.", "local."]
        if any(dev_host in host for dev_host in dev_hosts):
            return True
    except Exception:
        pass

    return False


def _get_scheme(request: Request) -> str:
    """Get the request scheme, with fallback to http."""
    try:
        # Honor X-Forwarded-Proto when present (common behind TLS-terminating proxies)
        try:
            xfp = request.headers.get("x-forwarded-proto")
            if xfp:
                return xfp.split(",")[0].strip().lower()
        except Exception:
            pass
        return getattr(request.url, "scheme", "http")
    except Exception:
        return "http"


def get_token_ttls() -> tuple[int, int]:
    """
    Get consistent TTLs for access and refresh tokens.

    Reads from environment variables:
    - JWT_EXPIRE_MINUTES: Access token TTL in minutes (default: 15)
    - JWT_REFRESH_EXPIRE_MINUTES: Refresh token TTL in minutes (default: 43200)

    Returns:
        Tuple[int, int]: (access_ttl_seconds, refresh_ttl_seconds)
    """
    # Access token TTL (default: 30 minutes)
    access_minutes = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))
    access_ttl = access_minutes * 60

    # Refresh token TTL (default: 1440 minutes = 1 day)
    refresh_minutes = int(os.getenv("JWT_REFRESH_EXPIRE_MINUTES", "1440"))
    refresh_ttl = refresh_minutes * 60

    return access_ttl, refresh_ttl


def format_cookie_header(
    key: str,
    value: str,
    max_age: int,
    secure: bool,
    samesite: str,
    path: str = "/",
    httponly: bool = True,
    domain: str = None,
) -> str:
    """
    Format a Set-Cookie header with consistent attributes.

    This is the only place that formats Set-Cookie headers, ensuring
    consistent attribute ordering and formatting across all cookies.

    Args:
        key: Cookie name
        value: Cookie value
        max_age: Max age in seconds
        secure: Whether cookie is secure
        samesite: SameSite attribute (lax, strict, none)
        path: Cookie path
        httponly: Whether cookie is HttpOnly
        domain: Cookie domain (None for host-only)

    Returns:
        str: Formatted Set-Cookie header
    """
    # Normalize SameSite value - use proper case
    samesite_map = {"lax": "Lax", "strict": "Strict", "none": "None"}
    ss = samesite_map.get(samesite.lower(), "Lax")

    parts = [
        f"{key}={value}",
        f"Max-Age={int(max_age)}",
        f"Path={path}",
        f"SameSite={ss}",
    ]

    if httponly:
        parts.append("HttpOnly")

    if secure:
        parts.append("Secure")

    if domain:
        parts.append(f"Domain={domain}")

    # Add Priority=High for critical auth cookies (legacy + canonical names)
    try:
        # Prefer centralized web cookie names when available
        from .web.cookies import NAMES as WEB_COOKIE_NAMES

        priority_names = {WEB_COOKIE_NAMES.access, WEB_COOKIE_NAMES.refresh, WEB_COOKIE_NAMES.session, "access_token", "refresh_token", "__session", "GSNH_AT", "GSNH_RT", "GSNH_SESS"}
    except Exception:
        priority_names = {"access_token", "refresh_token", "__session", "GSNH_AT", "GSNH_RT", "GSNH_SESS"}
    if key in priority_names:
        parts.append("Priority=High")

    return "; ".join(parts)


# Export the main functions for easy access
__all__ = ["get_cookie_config", "get_token_ttls", "format_cookie_header"]
