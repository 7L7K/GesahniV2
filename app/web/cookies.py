import logging
import os
import time
from datetime import UTC
from typing import NamedTuple

from app.cookie_config import format_cookie_header, get_cookie_config

try:  # Metrics are optional during tests/startup
    from app.metrics import COOKIE_CONFLICT
except Exception:  # pragma: no cover - metrics registry unavailable
    COOKIE_CONFLICT = None

logger = logging.getLogger(__name__)


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
        f"{_PREFIX}access_token",
        f"{_PREFIX}refresh_token",
        f"{_PREFIX}__session",
        "csrf_token",
    )
elif _CANON == "gsnh":
    NAMES = CookieNames(
        f"{_PREFIX}GSNH_AT", f"{_PREFIX}GSNH_RT", f"{_PREFIX}GSNH_SESS", "csrf_token"
    )
else:
    # legacy/classic
    NAMES = CookieNames(
        f"{_PREFIX}access_token",
        f"{_PREFIX}refresh_token",
        f"{_PREFIX}__session",
        "csrf_token",
    )

# Cookie aliases for backward compatibility (old gsn_* names)
if _CANON == "gsn":
    ACCESS_CANON, REFRESH_CANON = "gsn_access", "gsn_refresh"
else:
    ACCESS_CANON, REFRESH_CANON = "access_token", "refresh_token"

SESSION_CANON = os.getenv("SESSION_COOKIE_NAME", "__session")

# Cookie precedence order arrays - canonical first, then legacy
AT_ORDER = ["__Host-GSNH_AT", "GSNH_AT", "access_token", "gsn_access"]
RT_ORDER = ["__Host-GSNH_RT", "GSNH_RT", "refresh_token", "gsn_refresh"]
SESS_ORDER = ["__Host-GSNH_SESS", "GSNH_SESS", "__session", "session"]

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


def _schedule_legacy_cleanup(request, cookie_type: str, names: list[str]) -> None:
    """Record legacy cookie names to clear when we next write canonical cookies."""

    if not names:
        return
    if request is None:
        return
    try:
        state = request.state
    except AttributeError:
        return

    try:
        cleanup = getattr(state, "_legacy_cookie_cleanup", None)
        if not isinstance(cleanup, dict):
            cleanup = {}
        bucket = cleanup.setdefault(cookie_type, set())
        bucket.update(names)
        setattr(state, "_legacy_cookie_cleanup", cleanup)
    except Exception:
        # Best-effort scheduling; never block auth pipeline on cleanup tracking.
        pass


def pick_cookie(request, order: list[str]) -> tuple[str | None, str | None]:
    """Return first cookie from ``order`` and log/schedule cleanup for conflicts."""

    jar = getattr(request, "cookies", {}) or {}

    chosen_name: str | None = None
    chosen_value: str | None = None
    canonical = order[:2]

    for name in order:
        value = jar.get(name)
        if value:
            chosen_name = name
            chosen_value = value
            break

    if not chosen_name or not chosen_value:
        return None, None

    cookie_type = _get_cookie_type(chosen_name)
    conflicts: list[str] = []
    legacy_candidates: list[str] = []

    for name in order:
        if name == chosen_name:
            continue
        value = jar.get(name)
        if not value:
            continue
        if name not in canonical:
            legacy_candidates.append(name)
        if value != chosen_value:
            conflicts.append(name)

    if conflicts or (chosen_name not in canonical and legacy_candidates):
        try:
            logger.warning(
                "cookie_conflict",
                extra={
                    "chosen": chosen_name,
                    "chosen_is_canonical": chosen_name in canonical,
                    "conflicts": conflicts or legacy_candidates,
                    "cookie_type": cookie_type,
                },
            )
        except Exception:
            pass

        if COOKIE_CONFLICT is not None:
            try:
                COOKIE_CONFLICT.labels(cookie_type=cookie_type).inc()
            except Exception:
                pass

        # Schedule legacy deletions; prefer explicit conflicts, otherwise all legacy aliases.
        preferred = conflicts if conflicts else legacy_candidates
        cleanup_targets = [n for n in preferred if n not in canonical]
        if chosen_name not in canonical:
            cleanup_targets.append(chosen_name)
        cleanup_targets = list({name for name in cleanup_targets if name})
        _schedule_legacy_cleanup(request, cookie_type, cleanup_targets)

    return chosen_name, chosen_value


def _get_cookie_type(cookie_name: str) -> str:
    """Helper to determine cookie type for logging."""
    if any(cookie_name.endswith(suffix) for suffix in ['_AT', 'access']):
        return "access_token"
    elif any(cookie_name.endswith(suffix) for suffix in ['_RT', 'refresh']):
        return "refresh_token"
    elif any(cookie_name.endswith(suffix) for suffix in ['_SESS', 'session', '__session']):
        return "session"
    else:
        return "unknown"


def read_access_cookie(request) -> str | None:
    """Read access token cookie using precedence order."""
    name, value = pick_cookie(request, AT_ORDER)
    
    logger.info(f"🔍 COOKIE_READ_ACCESS: Reading access cookie", extra={
        "meta": {
            "cookie_name": name,
            "cookie_present": bool(value),
            "cookie_length": len(value) if value else 0,
            "all_cookies": list(request.cookies.keys()),
            "timestamp": time.time()
        }
    })
    
    return value


def read_refresh_cookie(request) -> str | None:
    """Read refresh token cookie using precedence order."""
    name, value = pick_cookie(request, RT_ORDER)
    
    logger.info(f"🔍 COOKIE_READ_REFRESH: Reading refresh cookie", extra={
        "meta": {
            "cookie_name": name,
            "cookie_present": bool(value),
            "cookie_length": len(value) if value else 0,
            "all_cookies": list(request.cookies.keys()),
            "timestamp": time.time()
        }
    })
    
    return value


def read_session_cookie(request) -> str | None:
    """Read session cookie using precedence order."""
    name, value = pick_cookie(request, SESS_ORDER)
    
    logger.info(f"🔍 COOKIE_READ_SESSION: Reading session cookie", extra={
        "meta": {
            "cookie_name": name,
            "cookie_present": bool(value),
            "cookie_length": len(value) if value else 0,
            "all_cookies": list(request.cookies.keys()),
            "timestamp": time.time()
        }
    })
    
    return value


def _append_cookie(
    resp,
    *,
    key: str,
    value: str,
    max_age: int,
    http_only: bool,
    same_site: str,
    domain: str | None,
    path: str,
    secure: bool,
    request=None,
) -> None:
    # Check for Partitioned cookie support (CHIPS)
    secure = True if secure is None else bool(secure)

    same_site_value = same_site or "Lax"

    # SameSite=None must force Secure=True
    if str(same_site_value).lower() == "none":
        secure = True

    # __Host- cookies must always have Path=/ and no Domain per RFC 6265bis
    if key.startswith("__Host-"):
        assert domain in {None, ""} and path == "/", "__Host- requires Path=/ and no Domain"
        domain = None
        path = "/"

    partitioned = False
    try:
        from app.settings import AUTH_ENABLE_PARTITIONED

        partitioned = bool(AUTH_ENABLE_PARTITIONED)
    except Exception:
        partitioned = os.getenv("ENABLE_PARTITIONED_COOKIES", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    header = format_cookie_header(
        key=key,
        value=value or "",
        max_age=max_age,
        secure=secure,
        samesite=same_site_value,
        path=path,
        httponly=http_only,
        domain=domain or None,
        partitioned=partitioned,
    )
    # Starlette Response supports headers.append("set-cookie", ...)
    resp.headers.append("set-cookie", header)

    # Emit cleanup headers for legacy aliases when scheduled
    cleanup_names: list[str] = []
    if request is not None:
        try:
            state = request.state
            cleanup = getattr(state, "_legacy_cookie_cleanup", None)
            if isinstance(cleanup, dict):
                cookie_type = _get_cookie_type(key)
                names = cleanup.get(cookie_type)
                if names:
                    cleanup_names = [n for n in names if n != key]
                    names.difference_update(cleanup_names)
                    if not names:
                        cleanup.pop(cookie_type, None)
                if cleanup_names:
                    setattr(state, "_legacy_cookie_cleanup", cleanup)
        except Exception:
            cleanup_names = []

    for alias in cleanup_names:
        try:
            removal = format_cookie_header(
                key=alias,
                value="",
                max_age=0,
                secure=secure,
                samesite=same_site_value,
                path=path,
                httponly=http_only,
                domain=domain or None,
                partitioned=False,
            )
            resp.headers.append("set-cookie", removal)
        except Exception:
            # Ignore cleanup failures; main cookie already written.
            continue


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
    request=None,
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
        request=request,
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
        request=request,
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
        request=request,
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
    **extras,
):
    """Public facade used across the codebase to set auth cookies consistently.

    Derives cookie attributes from centralized cookie configuration when a
    `request` is provided. Emits Set-Cookie headers via Response.headers.

    Accepts and ignores extra keyword arguments for forward compatibility
    (e.g., callers may pass identity or other metadata).
    """
    if extras:
        try:
            ignored = ",".join(sorted(extras.keys()))
        except Exception:
            ignored = "<unprintable>"
        logger.warning("set_auth_cookies: ignoring extra kwargs: %s", ignored)

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

    # Access cookie: only write when non-empty
    if access:
        _append_cookie(
            resp,
            key=NAMES.access,
            value=access,
            max_age=access_ttl,
            http_only=True,
            same_site=same_site.capitalize(),
            domain=domain,
            path=path,
            secure=secure,
            request=request,
        )
    if refresh is not None and refresh != "":
        _append_cookie(
            resp,
            key=NAMES.refresh,
            value=refresh,
            max_age=refresh_ttl,
            http_only=True,
            same_site=same_site.capitalize(),
            domain=domain,
            path=path,
            secure=secure,
            request=request,
        )
    if session_id is not None and session_id != "":
        _append_cookie(
            resp,
            key=NAMES.session,
            value=session_id,
            max_age=access_ttl,
            http_only=True,
            same_site=same_site.capitalize(),
            domain=domain,
            path=path,
            secure=secure,
            request=request,
        )

    # Validation logging: cookie status summary
    try:
        access_set = bool(access)
        refresh_set = bool(refresh is not None and refresh != "")
        session_set = bool(session_id is not None and session_id != "")
        logger.info(
            f"set_auth_cookies: access={access_set} refresh={refresh_set} session={session_set} "
            f"samesite={same_site} secure={secure}"
        )
    except Exception:
        pass  # Best-effort logging, don't fail on logging errors


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
    sec = (
        True
        if same_site.lower() == "none"
        else (True if secure is None else bool(secure))
    )
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
    _append_cookie(
        resp,
        key=state_cookie_name,
        value="",
        max_age=0,
        http_only=True,
        same_site="Lax",
        domain=None,
        path="/",
        secure=True,
    )
    _append_cookie(
        resp,
        key=next_cookie_name,
        value="",
        max_age=0,
        http_only=False,
        same_site="Lax",
        domain=None,
        path="/",
        secure=True,
    )


def clear_csrf(
    resp,
    *,
    same_site: str = "Lax",
    domain: str | None = None,
    path: str = "/",
    secure: bool | None = None,
):
    sec = (
        True
        if same_site.lower() == "none"
        else (True if secure is None else bool(secure))
    )
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


def set_device_cookie(
    resp, *, name: str, value: str, ttl: int, http_only: bool = False
):
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
    http_only_final = (
        http_only
        if http_only is not None
        else (httponly if httponly is not None else True)
    )
    # Determine SameSite preference
    ss = same_site or samesite or "Lax"
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


def set_auth_cookies_canon(
    resp, access: str, refresh: str, *, secure: bool, samesite: str, domain: str | None
):
    return cookie_facade.set_auth_cookies_canon(
        resp, access, refresh, secure=secure, samesite=samesite, domain=domain
    )


def set_csrf_cookie(resp, token: str, ttl: int, request=None):
    """
    DEPRECATED: Legacy CSRF cookie helper.

    CSRF protection has been migrated to header-token service.
    This function is kept for backward compatibility but should not be used for new code.
    Use /v1/auth/csrf endpoint and X-CSRF-Token header instead.
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

    set_csrf(
        resp,
        token,
        ttl=ttl,
        same_site=same_site.capitalize(),
        domain=domain,
        path=path,
        secure=secure,
    )


def set_oauth_state_cookie(
    resp, state: str, request=None, ttl: int = 600, provider: str = "oauth"
):
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
        _append_cookie(
            resp,
            key=key,
            value="",
            max_age=0,
            http_only=True,
            same_site=same_site,
            domain=domain,
            path=path,
            secure=secure,
        )
    # Legacy aliases
    for key in ("access_token", "refresh_token", "__session"):
        _append_cookie(
            resp,
            key=key,
            value="",
            max_age=0,
            http_only=True,
            same_site=same_site,
            domain=domain,
            path=path,
            secure=secure,
        )

    try:
        csrf_same_site = same_site
    except Exception:
        csrf_same_site = "Lax"

    _append_cookie(
        resp,
        key=NAMES.csrf,
        value="",
        max_age=0,
        http_only=False,
        same_site=csrf_same_site,
        domain=domain,
        path=path,
        secure=secure if str(csrf_same_site).lower() == "none" else secure,
    )


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
    """Read the access token cookie with canonical and legacy fallbacks.

    Canonical name comes from NAMES.access (default: GSNH_AT). Some clients/tests
    may still set legacy names (access_token). Read both to avoid whoami
    failures when only legacy cookies are present.
    """
    canonical = req.cookies.get(NAMES.access)
    if canonical:
        return canonical

    # Check for legacy cookie
    legacy = req.cookies.get("access_token")
    if legacy:
        try:
            logger.info(
                "auth.legacy_cookie_used",
                extra={
                    "meta": {
                        "name": "access_token",
                        "canonical_name": NAMES.access,
                        "action": "read",
                        "success": True,
                        "location": "web.cookies.read_access_cookie",
                    }
                },
            )
        except Exception:
            pass  # Best effort logging
        return legacy

    return None


def read_refresh_cookie(req):
    """Read the refresh token cookie with canonical and legacy fallbacks."""
    canonical = req.cookies.get(NAMES.refresh)
    if canonical:
        return canonical

    # Check for legacy cookie
    legacy = req.cookies.get("refresh_token")
    if legacy:
        try:
            logger.info(
                "auth.legacy_cookie_used",
                extra={
                    "meta": {
                        "name": "refresh_token",
                        "canonical_name": NAMES.refresh,
                        "action": "read",
                        "success": True,
                        "location": "web.cookies.read_refresh_cookie",
                    }
                },
            )
        except Exception:
            pass  # Best effort logging
        return legacy

    return None


def read_session_cookie(req):
    """Read the session cookie with canonical and legacy fallbacks."""
    canonical = req.cookies.get(NAMES.session)
    if canonical:
        return canonical

    # Check for legacy cookies in order of preference
    legacy_names = ["__session", "session"]
    for legacy_name in legacy_names:
        legacy = req.cookies.get(legacy_name)
        if legacy:
            try:
                logger.info(
                    "auth.legacy_cookie_used",
                    extra={
                        "meta": {
                            "name": legacy_name,
                            "canonical_name": NAMES.session,
                            "action": "read",
                            "success": True,
                            "location": "web.cookies.read_session_cookie",
                        }
                    },
                )
            except Exception:
                pass  # Best effort logging
            return legacy

    return None


# Centralized cookie operations with logging
log = logging.getLogger("cookie.ops")

def set_cookie(resp, *, name, value, max_age=86400, **kw):
    header = format_cookie_header(key=name, value=value, max_age=max_age, **kw)  # your existing formatter
    resp.headers.append("set-cookie", header)
    log.info("[COOKIE.OP] set %s path=%s samesite=%s secure=%s domain=%s httponly=%s",
             name, kw.get("path"), kw.get("samesite"), kw.get("secure"), kw.get("domain"), kw.get("httponly"))

def clear_cookie(resp, *, name, **kw):
    # Ensure required parameters have defaults for clearing cookies
    secure = kw.get("secure", True)
    samesite = kw.get("samesite", "Lax")
    header = format_cookie_header(key=name, value="", max_age=0, secure=secure, samesite=samesite, **kw)
    resp.headers.append("set-cookie", header)
    log.info("[COOKIE.OP] clear %s path=%s", name, kw.get("path"))


__all__ = [
    "CookieNames",
    "NAMES",
    "ACCESS_CANON",
    "REFRESH_CANON",
    "SESSION_CANON",
    "ACCESS_ALIASES",
    "REFRESH_ALIASES",
    "get_any",
    "pick_cookie",
    "set_cookie",
    "clear_cookie",
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
