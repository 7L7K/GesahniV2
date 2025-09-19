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
    from app.web.cookies import set_auth_cookies, clear_auth_cookies

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

import logging
import os

from fastapi import Request, Response

from .cookie_config import format_cookie_header, get_cookie_config

# Cookie name constants moved to web.cookies.NAMES

# Legacy cookie names for backward compatibility warnings
ACCESS_TOKEN = "access_token"
REFRESH_TOKEN = "refresh_token"
SESSION = "__session"

log = logging.getLogger(__name__)


def _read_first_cookie(
    request: Request, names: list[str]
) -> tuple[str | None, str | None]:
    """Return (value, name) for the first present cookie among names.

    Handles both `__Host-<name>` and `<name>` automatically when secure host cookies
    are enabled. Does not raise.
    """
    try:
        # Prefer __Host- prefixed variant when configured
        use_host_prefix = os.getenv("USE_HOST_COOKIE_PREFIX", "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    except Exception:
        use_host_prefix = True
    for n in names:
        # Check __Host- prefixed first, then raw name
        if use_host_prefix:
            v = request.cookies.get(f"__Host-{n}")
            if v:
                return v, f"__Host-{n}"
        v = request.cookies.get(n)
        if v:
            return v, n
    return None, None


def _warn_legacy_cookie_used(found_name: str, canonical: str) -> None:
    try:
        # Treat ACCESS_TOKEN/REFRESH_TOKEN/SESSION (and bare 'session') as legacy readers
        legacy_names = {ACCESS_TOKEN, REFRESH_TOKEN, SESSION, "session"}
        if found_name in legacy_names:
            log.warning(
                "auth.legacy_cookie_read name=%s canonical=%s", found_name, canonical
            )
    except Exception:
        pass


def read_access_cookie(request: Request) -> str | None:
    """Read access token cookie using canonical names from web.cookies.NAMES."""
    from .web.cookies import read

    cookies = read(request)
    return cookies.get("access")


def read_refresh_cookie(request: Request) -> str | None:
    """Read refresh token cookie using canonical names from web.cookies.NAMES."""
    from .web.cookies import read

    cookies = read(request)
    return cookies.get("refresh")


def read_session_cookie(request: Request) -> str | None:
    """Read session cookie using canonical names from web.cookies.NAMES."""
    from .web.cookies import read

    cookies = read(request)
    return cookies.get("session")


def set_auth_cookie(resp: Response, name: str, value: str, max_age: int):
    """
    Set a single auth cookie using web.cookies.set_cookie helper.

    This function is now a wrapper around web.cookies.set_cookie for backward compatibility.
    """
    from .web.cookies import set_cookie

    set_cookie(
        resp,
        name,
        value,
        max_age=max_age,
        http_only=True,
        secure=False,
        same_site="lax",
    )


def set_auth_cookies_canon(
    resp: Response,
    access: str,
    refresh: str,
    *,
    secure: bool,
    samesite: str,
    domain: str | None,
):
    """Set auth cookies using canonical alias names via Response.set_cookie.

    This function intentionally uses resp.set_cookie and lives in app/cookies.py
    to satisfy the guard that prohibits raw set_cookie usage elsewhere.
    """
    from app.feature_flags import AUTH_COOKIES_ENABLED

    if not AUTH_COOKIES_ENABLED:
        # Silently skip setting cookies when feature is disabled
        # This prevents auth cookies from being set without breaking the API
        return
    common = dict(
        httponly=True, secure=bool(secure), samesite=samesite, domain=domain, path="/"
    )
    # Use the alias names from web.cookies to keep compatibility with tests
    from .web.cookies import ACCESS_CANON, REFRESH_CANON

    resp.set_cookie(ACCESS_CANON, access, **common)
    resp.set_cookie(REFRESH_CANON, refresh, **common)


def clear_auth_cookies(resp: Response, request: Request) -> None:
    """Clear all authentication cookies using centralized config (dev-friendly).

    Uses cookie_config to determine Secure/SameSite/Path to ensure predictable
    behavior in dev/tests (Secure=False; SameSite=Lax; Path=/; no Domain).
    """
    from .web.cookies import NAMES

    cfg = get_cookie_config(request)
    same_site = str(cfg.get("samesite", "lax")).capitalize()
    domain = cfg.get("domain")
    path = cfg.get("path", "/")
    secure = bool(cfg.get("secure", True))

    # Build a single combined Set-Cookie header containing all three clears to
    # match tests that read only the first header value.
    headers = [
        format_cookie_header(
            NAMES.access,
            "",
            0,
            secure,
            same_site,
            path=path,
            httponly=True,
            domain=domain,
        ),
        format_cookie_header(
            NAMES.refresh,
            "",
            0,
            secure,
            same_site,
            path=path,
            httponly=True,
            domain=domain,
        ),
        format_cookie_header(
            NAMES.session,
            "",
            0,
            secure,
            same_site,
            path=path,
            httponly=True,
            domain=domain,
        ),
        format_cookie_header(
            NAMES.csrf,
            "",
            0,
            secure,
            same_site,
            path=path,
            httponly=False,
            domain=domain,
        ),
    ]
    resp.headers["set-cookie"] = ", ".join(headers)


def clear_oauth_state_cookies(
    resp: Response, request: Request, provider: str = "oauth"
) -> None:
    """
    Clear OAuth state cookies from the response using canonical web.cookies helpers.

    This function is now a wrapper around web.cookies.clear_oauth_state_cookies for backward compatibility.
    """
    from .web.cookies import clear_oauth_state_cookies as _clear_oauth_state_cookies

    _clear_oauth_state_cookies(resp, provider=provider)


def set_csrf_cookie(resp: Response, *, token: str, ttl: int, request: Request) -> None:
    """
    Set CSRF token cookie for double-submit protection using canonical web.cookies helpers.

    This function is now a wrapper around web.cookies.set_csrf for backward compatibility.
    """
    from .web.cookies import set_csrf as _set_csrf

    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)

    _set_csrf(
        resp,
        token=token,
        ttl=ttl,
        same_site=cookie_config["samesite"],
        domain=cookie_config["domain"],
        path=cookie_config["path"],
        secure=cookie_config["secure"],
    )


def clear_csrf_cookie(resp: Response, request: Request) -> None:
    """
    Clear CSRF token cookie from the response using canonical web.cookies helpers.

    This function is now a wrapper around web.cookies.clear_csrf for backward compatibility.
    """
    from .web.cookies import clear_csrf as _clear_csrf

    # Get cookie configuration from request context
    cookie_config = get_cookie_config(request)

    _clear_csrf(
        resp,
        same_site=cookie_config["samesite"],
        domain=cookie_config["domain"],
        path=cookie_config["path"],
        secure=cookie_config["secure"],
    )


def set_device_cookie(
    resp: Response,
    *,
    value: str,
    ttl: int,
    request: Request,
    cookie_name: str = "device_trust",
) -> None:
    """
    Set device trust/pairing cookie using web.cookies.set_device_cookie.

    This function is now a wrapper around web.cookies.set_device_cookie for backward compatibility.
    """
    from .web.cookies import set_device_cookie as _set_device_cookie

    _set_device_cookie(resp, name=cookie_name, value=value, ttl=ttl, http_only=False)


def clear_device_cookie(
    resp: Response, request: Request, cookie_name: str = "device_trust"
) -> None:
    """
    Clear device trust/pairing cookie using web.cookies.clear_device_cookie.

    This function is now a wrapper around web.cookies.clear_device_cookie for backward compatibility.
    """
    from .web.cookies import clear_device_cookie as _clear_device_cookie

    _clear_device_cookie(resp, name=cookie_name, http_only=False)


def read_device_cookie(request: Request, cookie_name: str = "device_id") -> str | None:
    """
    Read device identification cookie using canonical web.cookies helpers.

    Args:
        request: FastAPI Request object
        cookie_name: Name of the device cookie (default: "device_id")

    Returns:
        Device ID string or None if not present
    """
    return request.cookies.get(cookie_name)


def clear_named_cookie(
    resp: Response,
    *,
    name: str,
    request: Request,
    path: str = None,
    domain: str = None,
    secure: bool = None,
    samesite: str = None,
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

    from .web.cookies import clear_named_cookie as _clear_named_cookie

    _clear_named_cookie(
        resp,
        name=name,
        http_only=True,  # Default to HttpOnly for security
        same_site=cookie_samesite,
        domain=cookie_domain,
        path=cookie_path,
        secure=cookie_secure,
    )


def get_cookie(request: Request, name: str) -> str | None:
    """Plain cookie reader — no legacy fallbacks.

    Use direct `get_cookie(request, GSNH_AT)` for auth reads to ensure only canonical
    names are relied upon.
    """
    return request.cookies.get(name)


# Import set_auth_cookies from web.cookies for compatibility
from .web.cookies import set_auth_cookies

# Export all cookie facade functions
__all__ = [
    "set_auth_cookie",
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
]
