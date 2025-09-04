import os
from typing import NamedTuple

class CookieNames(NamedTuple):
    access: str
    refresh: str
    session: str
    csrf: str

_CANON = os.getenv("COOKIE_CANON", "legacy").lower()
_HOST  = os.getenv("USE_HOST_COOKIE_PREFIX", "0") == "1"
_PREFIX = "__Host-" if (_CANON == "host" or _HOST) else ""

if _CANON == "host":
    NAMES = CookieNames(f"{_PREFIX}access_token", f"{_PREFIX}refresh_token", f"{_PREFIX}__session", "csrf_token")
elif _CANON == "gsnh":
    NAMES = CookieNames(f"{_PREFIX}GSNH_AT", f"{_PREFIX}GSNH_RT", f"{_PREFIX}GSNH_SESS", "csrf_token")
else:
    NAMES = CookieNames(f"{_PREFIX}access_token", f"{_PREFIX}refresh_token", f"{_PREFIX}__session", "csrf_token")

def set_cookie(resp, key: str, value: str, *, max_age: int, http_only=True, same_site="Lax", domain=None, path="/", secure=None):
    secure = True if secure is None else secure
    resp.set_cookie(key=key, value=value, max_age=max_age, path=path, domain=domain, secure=secure, httponly=http_only, samesite=same_site)

def set_auth(resp, access: str, refresh: str, session_id: str, *, access_ttl: int, refresh_ttl: int, same_site="Lax", domain=None, path="/"):
    set_cookie(resp, NAMES.access, access, max_age=access_ttl, same_site=same_site, domain=domain, path=path)
    set_cookie(resp, NAMES.refresh, refresh, max_age=refresh_ttl, same_site=same_site, domain=domain, path=path)
    set_cookie(resp, NAMES.session, session_id, max_age=refresh_ttl, same_site=same_site, domain=domain, path=path)

def set_csrf(resp, token: str, *, ttl: int = 1800, same_site="Lax", domain=None, path="/", secure=None):
    """
    Set CSRF token cookie with special handling for cross-site scenarios.
    CSRF tokens need to be accessible to JavaScript so they're not HttpOnly.
    When SameSite=None, they must also be Secure=True.
    """
    # CSRF cookies need special handling for cross-site scenarios
    if same_site == "none":
        # Ensure Secure=True when SameSite=None
        secure = True
    elif secure is None:
        # For same-origin scenarios, use default secure behavior
        secure = True

    set_cookie(resp, NAMES.csrf, token, max_age=ttl, http_only=False, same_site=same_site, domain=domain, path=path, secure=secure)

def set_oauth_state_cookies(resp, *, state: str, next_url: str, ttl: int = 600, provider: str = "oauth", code_verifier: str | None = None, session_id: str | None = None):
    """
    Set OAuth state cookies for OAuth flows.

    Sets state, next_url, and optionally code_verifier cookies for CSRF protection and redirect handling.
    """
    # Set OAuth state cookie (HttpOnly for security)
    state_cookie_name = f"{provider}_state"
    set_cookie(resp, state_cookie_name, state, max_age=ttl, http_only=True)

    # Set OAuth next URL cookie (not HttpOnly so client can read it)
    next_cookie_name = f"{provider}_next"
    set_cookie(resp, next_cookie_name, next_url, max_age=ttl, http_only=False)

    # Set code verifier if provided (PKCE)
    if code_verifier:
        verifier_cookie_name = f"{provider}_code_verifier"
        set_cookie(resp, verifier_cookie_name, code_verifier, max_age=ttl, http_only=True)

    # Set session ID if provided
    if session_id:
        session_cookie_name = f"{provider}_session"
        set_cookie(resp, session_cookie_name, session_id, max_age=ttl, http_only=True)

def clear_oauth_state_cookies(resp, *, provider: str = "oauth"):
    """
    Clear OAuth state cookies from the response.
    """
    # Clear OAuth state cookies with Max-Age=0
    state_cookie_name = f"{provider}_state"
    next_cookie_name = f"{provider}_next"
    verifier_cookie_name = f"{provider}_code_verifier"
    session_cookie_name = f"{provider}_session"

    # Clear the main OAuth cookies
    set_cookie(resp, state_cookie_name, "", max_age=0, http_only=True)
    set_cookie(resp, next_cookie_name, "", max_age=0, http_only=False)
    set_cookie(resp, verifier_cookie_name, "", max_age=0, http_only=True)
    set_cookie(resp, session_cookie_name, "", max_age=0, http_only=True)

def clear_csrf(resp, *, same_site="Lax", domain=None, path="/", secure=None):
    """
    Clear CSRF token cookie from the response.
    """
    # CSRF cookies need special handling for cross-site scenarios
    if same_site == "none":
        # Ensure Secure=True when SameSite=None
        secure = True
    elif secure is None:
        # For same-origin scenarios, use default secure behavior
        secure = True

    set_cookie(resp, NAMES.csrf, "", max_age=0, http_only=False, same_site=same_site, domain=domain, path=path, secure=secure)

def set_device_cookie(resp, *, name: str, value: str, ttl: int, http_only=False):
    """
    Set a device trust/pairing cookie.
    Device cookies are typically not HttpOnly so they can be read by JavaScript.
    """
    set_cookie(resp, name, value, max_age=ttl, http_only=http_only)

def clear_device_cookie(resp, *, name: str, http_only=False):
    """
    Clear a device trust/pairing cookie from the response.
    """
    set_cookie(resp, name, "", max_age=0, http_only=http_only)

def read(req):
    c = req.cookies
    return {"access": c.get(NAMES.access), "refresh": c.get(NAMES.refresh), "session": c.get(NAMES.session), "csrf": c.get(NAMES.csrf)}


# Backwards-compatible helpers (thin wrappers to keep existing call sites working)
def set_auth_cookies(resp, *, access: str, refresh: str | None = None, session_id: str | None = None, access_ttl: int = 0, refresh_ttl: int = 0, request=None, identity=None):
    """Compatibility wrapper for the older API `set_auth_cookies`.

    Writes a single set of auth cookies (access, refresh, session) using the
    canonical names defined in `NAMES`.
    """
    # Ensure required args exist
    if access is None:
        return
    # Use provided TTLs
    set_auth(resp, access, refresh or "", session_id or "", access_ttl=access_ttl, refresh_ttl=refresh_ttl)


def clear_auth_cookies(resp, request=None):
    """Clear canonical auth cookies (access, refresh, session)."""
    # Clear each canonical cookie by setting Max-Age=0
    resp.set_cookie(key=NAMES.access, value="", max_age=0, path="/", httponly=True, secure=True, samesite="Lax")
    resp.set_cookie(key=NAMES.refresh, value="", max_age=0, path="/", httponly=True, secure=True, samesite="Lax")
    resp.set_cookie(key=NAMES.session, value="", max_age=0, path="/", httponly=True, secure=True, samesite="Lax")


def set_csrf_cookie(resp, token: str, ttl: int, request=None):
    # Wrapper for legacy name
    set_csrf(resp, token, ttl=ttl)


def set_named_cookie(resp, *, name: str, value: str, ttl: int, request=None, path: str = "/", httponly: bool = True, samesite: str | None = None, secure: bool | None = None, domain: str | None = None):
    set_cookie(resp, name, value, max_age=ttl, http_only=httponly, same_site=(samesite or "Lax"), domain=domain, path=path, secure=secure)


def set_oauth_state_cookies(resp, *, state: str, next_url: str, request=None, ttl: int = 600, provider: str = "oauth", code_verifier: str | None = None, session_id: str | None = None):
    """Set OAuth state and next cookies using the simple `set_cookie` helper.

    This replicates the previous behavior in a minimal way: provider_state
    (HttpOnly), provider_next (not HttpOnly), optional provider_code_verifier
    (HttpOnly), and optional provider_session (HttpOnly).
    """
    state_name = f"{provider}_state"
    next_name = f"{provider}_next"
    set_cookie(resp, state_name, state, max_age=ttl, http_only=True, same_site="Lax")
    set_cookie(resp, next_name, next_url, max_age=ttl, http_only=False, same_site="Lax")
    if code_verifier:
        set_cookie(resp, f"{provider}_code_verifier", code_verifier, max_age=ttl, http_only=True, same_site="Lax")
    if session_id:
        set_cookie(resp, f"{provider}_session", session_id, max_age=ttl, http_only=True, same_site="Lax")


def read_access_cookie(req):
    return req.cookies.get(NAMES.access)


def read_refresh_cookie(req):
    return req.cookies.get(NAMES.refresh)


def read_session_cookie(req):
    return req.cookies.get(NAMES.session)


__all__ = [
    "CookieNames",
    "NAMES",
    "set_cookie",
    "set_auth",
    "set_auth_cookies",
    "clear_auth_cookies",
    "set_csrf",
    "set_csrf_cookie",
    "set_named_cookie",
    "set_oauth_state_cookies",
    "read",
    "read_access_cookie",
    "read_refresh_cookie",
    "read_session_cookie",
]


