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

from fastapi import Request, Response
import logging
import os

from . import cookie_config as cookie_cfg
from .cookie_config import format_cookie_header, get_cookie_config
# Cookie name constants moved to web.cookies.NAMES

log = logging.getLogger(__name__)

def _read_first_cookie(request: Request, names: list[str]) -> tuple[str | None, str | None]:
    """Return (value, name) for the first present cookie among names.

    Handles both `__Host-<name>` and `<name>` automatically when secure host cookies
    are enabled. Does not raise.
    """
    try:
        # Prefer __Host- prefixed variant when configured
        use_host_prefix = os.getenv("USE_HOST_COOKIE_PREFIX", "1").strip().lower() in {"1","true","yes","on"}
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
            log.warning("auth.legacy_cookie_read name=%s canonical=%s", found_name, canonical)
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
    set_cookie(resp, name, value, max_age=max_age, http_only=True, secure=False, same_site="lax")


def set_auth_cookies(
    resp: Response,
    *,
    access: str,
    refresh: str | None = None,
    session_id: str | None = None,
    access_ttl: int,
    refresh_ttl: int,
    request: Request,
    identity: dict | None = None,
) -> None:
    """
    Set authentication cookies on the response using the canonical web.cookies helpers.

    This function is now a thin wrapper around web.cookies.set_auth for backward compatibility.
    """
    from .web.cookies import set_auth

    # Set the canonical cookies
    if session_id:
        set_auth(resp, access, refresh or "", session_id, access_ttl=access_ttl, refresh_ttl=refresh_ttl)
    else:
        # Set access and refresh cookies only
        from .web.cookies import set_cookie, NAMES
        set_cookie(resp, NAMES.access, access, max_age=access_ttl)
        if refresh and refresh.strip():
            set_cookie(resp, NAMES.refresh, refresh, max_age=refresh_ttl)

    # Handle session store persistence for backward compatibility
    if session_id:
        try:
            from .session_store import get_session_store
            store = get_session_store()

            # Prefer provided identity payload (caller-side mint payload)
            ident = identity
            exp_s: int | None = None

            if not ident:
                # Fallback: safe decode of freshly-minted access token to extract identity
                try:
                    import os
                    from .security import jwt_decode as _decode

                    leeway = int(os.getenv("JWT_CLOCK_SKEW_S", "60") or 60)
                    secret = os.getenv("JWT_SECRET")
                    if secret:
                        claims = _decode(access, secret, algorithms=["HS256"], leeway=leeway)
                        ident = dict(claims) if isinstance(claims, dict) else None
                except Exception:
                    ident = None

            # Extract exp for TTL
            try:
                if ident and isinstance(ident, dict):
                    exp_s = int(ident.get("exp")) if ident.get("exp") else None
            except Exception:
                exp_s = None

            if ident and exp_s:
                # Never fail login if store write fails; best-effort only
                try:
                    store.set_session_identity(session_id, ident, exp_s)
                except Exception:
                    pass
        except Exception:
            # Never block cookie writes on identity persistence errors
            pass


def clear_auth_cookies(resp: Response, request: Request) -> None:
    """
    Clear all authentication cookies from the response using canonical web.cookies helpers.

    This function is now a wrapper around web.cookies.set_cookie with max_age=0 for backward compatibility.
    """
    from .web.cookies import set_cookie, NAMES

    # Clear the canonical cookies
    set_cookie(resp, NAMES.access, "", max_age=0)
    set_cookie(resp, NAMES.refresh, "", max_age=0)
    set_cookie(resp, NAMES.session, "", max_age=0)


def set_oauth_state_cookies(
    resp: Response,
    *,
    state: str,
    next_url: str,
    request: Request,
    ttl: int = 600,  # Default 10 minutes
    provider: str = "oauth",  # Provider-specific cookie prefix
    code_verifier: str | None = None,  # PKCE code verifier for enhanced security
    session_id: str | None = None,
) -> None:
    """
    Set OAuth state cookies for Google/Apple OAuth flows using canonical web.cookies helpers.

    This function is now a wrapper around web.cookies.set_oauth_state_cookies for backward compatibility.
    """
    from .web.cookies import set_oauth_state_cookies as _set_oauth_state_cookies

    _set_oauth_state_cookies(
        resp,
        state=state,
        next_url=next_url,
        ttl=ttl,
        provider=provider,
        code_verifier=code_verifier,
        session_id=session_id,
    )


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


def set_named_cookie(
    resp: Response,
    *,
    name: str,
    value: str,
    ttl: int,
    request: Request,
    path: str = "/",
    httponly: bool = True,
    samesite: str | None = None,
    secure: bool | None = None,
    domain: str | None = None,
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
    cookie_samesite = (samesite or cookie_config["samesite"]).lower()
    cookie_secure = cookie_config["secure"] if secure is None else bool(secure)

    # Enforce policy: SameSite=None is only valid with Secure=True
    if cookie_samesite == "none":
        cookie_secure = True

    from .web.cookies import set_named_cookie as _set_named_cookie
    _set_named_cookie(
        resp,
        name=name,
        value=value,
        ttl=ttl,
        http_only=httponly,
        same_site=cookie_samesite,
        domain=cookie_domain,
        path=cookie_path,
        secure=cookie_secure,
    )


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
