import os
from datetime import UTC
from typing import NamedTuple

from app.cookie_config import format_cookie_header, get_cookie_config


class CookieNames(NamedTuple):
    access: str
    refresh: str
    session: str
    csrf: str


# Canon selection: default to "gsnh" which tests expect as canonical
_CANON = os.getenv("COOKIE_CANON", "gsnh").lower()
_HOST = os.getenv("USE_HOST_COOKIE_PREFIX", "0").strip() in {"1", "true", "yes", "on"}
_PREFIX = "__Host-" if (_CANON == "host" or _HOST) else ""

if _CANON == "host":
    NAMES = CookieNames(
        f"{_PREFIX}access_token", f"{_PREFIX}refresh_token", f"{_PREFIX}__session", "csrf_token"
    )
elif _CANON == "gsnh":
    NAMES = CookieNames(
        f"{_PREFIX}GSNH_AT", f"{_PREFIX}GSNH_RT", f"{_PREFIX}GSNH_SESS", "csrf_token"
    )
else:
    # legacy/classic
    NAMES = CookieNames(
        f"{_PREFIX}access_token", f"{_PREFIX}refresh_token", f"{_PREFIX}__session", "csrf_token"
    )

# Cookie aliases for backward compatibility (old gsn_* names)
if _CANON == "gsn":
    ACCESS_CANON, REFRESH_CANON = "gsn_access", "gsn_refresh"
else:
    ACCESS_CANON, REFRESH_CANON = "access_token", "refresh_token"

SESSION_CANON = os.getenv("SESSION_COOKIE_NAME", "__session")

ACCESS_ALIASES = {ACCESS_CANON, "access_token", "gsn_access"}
REFRESH_ALIASES = {REFRESH_CANON, "refresh_token", "gsn_refresh"}


def get_any(req, names: set[str]) -> str | None:
    """Get the first available cookie value from a set of possible names."""
    jar = req.cookies or {}
    for n in names:
        v = jar.get(n)
        if v:
            return v
    return None


def _append_cookie(resp, *, key: str, value: str, max_age: int, http_only: bool, same_site: str, domain: str | None, path: str, secure: bool) -> None:
    header = format_cookie_header(
        key=key, value=value or "", max_age=max_age, secure=secure, samesite=same_site, path=path, httponly=http_only, domain=domain or None
    )
    # Starlette Response supports headers.append("set-cookie", ...)
    resp.headers.append("set-cookie", header)


def set_cookie(
    resp,
    key: str,
    value: str,
    *,
    max_age: int,
    http_only: bool = True,
    same_site: str = "Lax",
    domain: str | None = None,
    path: str = "/",
    secure: bool | None = None,
):
    # Default to secure=True unless explicitly overridden by caller
    sec = True if secure is None else bool(secure)
    _append_cookie(
        resp,
        key=key,
        value=value,
        max_age=max_age,
        http_only=http_only,
        same_site=same_site,
        domain=domain,
        path=path,
        secure=sec,
    )


def set_auth(
    resp,
    access: str,
    refresh: str,
    session_id: str,
    *,
    access_ttl: int,
    refresh_ttl: int,
    same_site: str = "Lax",
    domain: str | None = None,
    path: str = "/",
    secure: bool = True,
):
    _append_cookie(
        resp,
        key=NAMES.access,
        value=access,
        max_age=access_ttl,
        http_only=True,
        same_site=same_site,
        domain=domain,
        path=path,
        secure=secure,
    )
    _append_cookie(
        resp,
        key=NAMES.refresh,
        value=refresh,
        max_age=refresh_ttl,
        http_only=True,
        same_site=same_site,
        domain=domain,
        path=path,
        secure=secure,
    )
    _append_cookie(
        resp,
        key=NAMES.session,
        value=session_id,
        max_age=access_ttl,  # session follows access TTL
        http_only=True,
        same_site=same_site,
        domain=domain,
        path=path,
        secure=secure,
    )


def set_auth_cookies(
    resp,
    *,
    access: str,
    refresh: str | None = None,
    session_id: str | None = None,
    access_ttl: int,
    refresh_ttl: int,
    request=None,
):
    """Public facade used across the codebase to set auth cookies consistently.

    Derives cookie attributes from centralized cookie configuration when a
    `request` is provided. Emits Set-Cookie headers via Response.headers.
    """
    same_site = "lax"
    domain = None
    path = "/"
    secure = True

    try:
        if request is not None:
            cfg = get_cookie_config(request)
            if cfg:
                same_site = cfg.get("samesite", "lax")
                domain = cfg.get("domain")
                path = cfg.get("path", "/")
                secure = bool(cfg.get("secure", True))
    except Exception:
        pass

    if access is None:
        return

    # Canonical cookie
    _append_cookie(resp, key=NAMES.access, value=access, max_age=access_ttl, http_only=True,
                   same_site=same_site.capitalize(), domain=domain, path=path, secure=secure)
    if refresh is not None and refresh != "":
        _append_cookie(resp, key=NAMES.refresh, value=refresh, max_age=refresh_ttl, http_only=True,
                       same_site=same_site.capitalize(), domain=domain, path=path, secure=secure)
    if session_id is not None and session_id != "":
        _append_cookie(resp, key=NAMES.session, value=session_id, max_age=access_ttl, http_only=True,
                       same_site=same_site.capitalize(), domain=domain, path=path, secure=secure)


def set_csrf(
    resp,
    token: str,
    *,
    ttl: int = 1800,
    same_site: str = "Lax",
    domain: str | None = None,
    path: str = "/",
    secure: bool | None = None,
):
    # SameSite=None forces Secure=True per spec
    sec = True if same_site.lower() == "none" else (True if secure is None else bool(secure))
    _append_cookie(
        resp,
        key=NAMES.csrf,
        value=token,
        max_age=ttl,
        http_only=False,
        same_site=same_site,
        domain=domain,
        path=path,
        secure=sec,
    )


def set_oauth_state_cookies(
    resp,
    *,
    state: str,
    next_url: str,
    ttl: int = 600,
    provider: str = "oauth",
    code_verifier: str | None = None,
    session_id: str | None = None,
    request=None,
):
    state_cookie_name = f"{provider}_state"
    next_cookie_name = f"{provider}_next"
    _append_cookie(
        resp,
        key=state_cookie_name,
        value=state,
        max_age=ttl,
        http_only=True,
        same_site="Lax",
        domain=None,
        path="/",
        secure=True,
    )
    _append_cookie(
        resp,
        key=next_cookie_name,
        value=next_url,
        max_age=ttl,
        http_only=False,
        same_site="Lax",
        domain=None,
        path="/",
        secure=True,
    )
    if code_verifier:
        _append_cookie(
            resp,
            key=f"{provider}_code_verifier",
            value=code_verifier,
            max_age=ttl,
            http_only=True,
            same_site="Lax",
            domain=None,
            path="/",
            secure=True,
        )
    if session_id:
        _append_cookie(
            resp,
            key=f"{provider}_session",
            value=session_id,
            max_age=ttl,
            http_only=True,
            same_site="Lax",
            domain=None,
            path="/",
            secure=True,
        )


def clear_oauth_state_cookies(resp, *, provider: str = "oauth"):
    state_cookie_name = f"{provider}_state"
    next_cookie_name = f"{provider}_next"
    # Clear only the two contract cookies: state (HttpOnly) and next (non-HttpOnly)
    _append_cookie(resp, key=state_cookie_name, value="", max_age=0, http_only=True,
                   same_site="Lax", domain=None, path="/", secure=True)
    _append_cookie(resp, key=next_cookie_name, value="", max_age=0, http_only=False,
                   same_site="Lax", domain=None, path="/", secure=True)


def clear_csrf(
    resp,
    *,
    same_site: str = "Lax",
    domain: str | None = None,
    path: str = "/",
    secure: bool | None = None,
):
    sec = True if same_site.lower() == "none" else (True if secure is None else bool(secure))
    _append_cookie(
        resp,
        key=NAMES.csrf,
        value="",
        max_age=0,
        http_only=False,
        same_site=same_site,
        domain=domain,
        path=path,
        secure=sec,
    )


def set_device_cookie(resp, *, name: str, value: str, ttl: int, http_only: bool = False):
    _append_cookie(
        resp,
        key=name,
        value=value,
        max_age=ttl,
        http_only=http_only,
        same_site="Lax",
        domain=None,
        path="/",
        secure=True,
    )


def clear_device_cookie(resp, *, name: str, http_only: bool = False):
    _append_cookie(
        resp,
        key=name,
        value="",
        max_age=0,
        http_only=http_only,
        same_site="Lax",
        domain=None,
        path="/",
        secure=True,
    )


def set_named_cookie(
    resp,
    *,
    name: str,
    value: str,
    ttl: int | None = None,
    # Accept legacy and alias parameter names used by tests
    max_age: int | None = None,
    http_only: bool | None = None,
    httponly: bool | None = None,
    same_site: str | None = None,
    samesite: str | None = None,
    domain: str | None = None,
    path: str = "/",
    secure: bool | None = None,
    # expires may be seconds (int/float) or datetime-like; keep type flexible
    expires: object | None = None,
    request=None,
):
    # Determine HttpOnly preference
    http_only_final = http_only if http_only is not None else (httponly if httponly is not None else True)
    # Determine SameSite preference
    ss = (same_site or samesite or "Lax")
    # Compute Max-Age precedence: expires (seconds) > max_age > ttl
    max_age_final: int | None = None
    try:
        if expires is not None:
            # If expires is datetime-like, convert to seconds from now; if numeric, treat as seconds
            from datetime import datetime
            if hasattr(expires, "timestamp"):
                now = datetime.now(UTC)
                exp_ts = expires.timestamp()  # type: ignore[attr-defined]
                max_age_final = max(0, int(exp_ts - now.timestamp()))
            else:
                max_age_final = max(0, int(float(expires)))
    except Exception:
        max_age_final = None
    if max_age_final is None:
        if max_age is not None:
            max_age_final = int(max_age)
        elif ttl is not None:
            max_age_final = int(ttl)
        else:
            max_age_final = 0
    # Determine Secure flag
    sec = True if secure is None else bool(secure)
    _append_cookie(
        resp,
        key=name,
        value=value,
        max_age=max_age_final,
        http_only=http_only_final,
        same_site=ss,
        domain=domain,
        path=path,
        secure=sec,
    )


def clear_named_cookie(
    resp,
    *,
    name: str,
    http_only: bool = True,
    same_site: str = "Lax",
    domain: str | None = None,
    path: str = "/",
    secure: bool | None = None,
    request=None,
):
    sec = True if secure is None else bool(secure)
    _append_cookie(
        resp,
        key=name,
        value="",
        max_age=0,
        http_only=http_only,
        same_site=same_site,
        domain=domain,
        path=path,
        secure=sec,
    )


def read(req):
    c = req.cookies or {}
    return {
        "access": c.get(NAMES.access),
        "refresh": c.get(NAMES.refresh),
        "session": c.get(NAMES.session),
        "csrf": c.get(NAMES.csrf),
    }


# Thin wrappers delegating to app.cookies for legacy helpers that intentionally
# call Response.set_cookie (guard test allows that only in app/cookies.py).
from app import cookies as cookie_facade


def set_auth_cookies_canon(resp, access: str, refresh: str, *, secure: bool, samesite: str, domain: str | None):
    return cookie_facade.set_auth_cookies_canon(
        resp, access, refresh, secure=secure, samesite=samesite, domain=domain
    )


def set_csrf_cookie(resp, token: str, ttl: int, request=None):
    set_csrf(resp, token, ttl=ttl)


def set_oauth_state_cookie(resp, state: str, request=None, ttl: int = 600, provider: str = "oauth"):
    # Back-compat singular alias
    set_oauth_state_cookies(resp, state=state, next_url="", ttl=ttl, provider=provider)


def clear_auth_cookies(resp, request=None):
    # Clear canonical and legacy auth cookies by emitting Max-Age=0 cookies
    same_site = "Lax"
    domain = None
    path = "/"
    secure = True
    try:
        if request is not None:
            try:
                # Prefer facade to allow tests to patch app.cookies.get_cookie_config
                from app.cookies import get_cookie_config as _facade_cfg
                cfg = _facade_cfg(request)
            except Exception:
                cfg = get_cookie_config(request)
            if cfg:
                same_site = str(cfg.get("samesite", "lax")).capitalize()
                domain = cfg.get("domain")
                path = cfg.get("path", "/")
                secure = bool(cfg.get("secure", True))
    except Exception:
        pass
    # Canonical
    for key in (NAMES.access, NAMES.refresh, NAMES.session):
        _append_cookie(resp, key=key, value="", max_age=0, http_only=True, same_site=same_site, domain=domain, path=path, secure=secure)
    # Legacy aliases
    for key in ("access_token", "refresh_token", "__session"):
        _append_cookie(resp, key=key, value="", max_age=0, http_only=True, same_site=same_site, domain=domain, path=path, secure=secure)


def clear_all_auth(resp):
    """Clear all auth cookies including canonical names and aliases using delete_cookie.

    Kept for backwards compatibility with tests that assert delete_cookie usage.
    """
    for n in {
        ACCESS_CANON,
        REFRESH_CANON,
        "access_token",
        "refresh_token",
        "gsn_access",
        "gsn_refresh",
        SESSION_CANON,
    }:
        try:
            resp.delete_cookie(n, path="/")
        except Exception:
            # If response doesn't support delete_cookie (e.g., plain Mock), ignore
            pass


def clear_csrf_cookie(resp, request=None):
    # Back-compat alias for tests
    clear_csrf(resp)


def read_access_cookie(req):
    return req.cookies.get(NAMES.access)


def read_refresh_cookie(req):
    return req.cookies.get(NAMES.refresh)


def read_session_cookie(req):
    return req.cookies.get(NAMES.session)


__all__ = [
    "CookieNames",
    "NAMES",
    "ACCESS_CANON",
    "REFRESH_CANON",
    "SESSION_CANON",
    "ACCESS_ALIASES",
    "REFRESH_ALIASES",
    "get_any",
    "set_cookie",
    "set_auth",
    "set_auth_cookies_canon",
    "clear_all_auth",
    "set_auth_cookies",
    "clear_auth_cookies",
    "set_csrf",
    "set_csrf_cookie",
    "clear_csrf",
    "clear_csrf_cookie",
    "set_named_cookie",
    "clear_named_cookie",
    "set_oauth_state_cookie",
    "set_oauth_state_cookies",
    "clear_oauth_state_cookies",
    "read",
    "read_access_cookie",
    "read_refresh_cookie",
    "read_session_cookie",
]
