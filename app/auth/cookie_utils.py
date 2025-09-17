"""Cookie utilities for GesahniV2 authentication."""

import logging
import os
import random
from typing import TYPE_CHECKING

from fastapi import Response

if TYPE_CHECKING:
    from fastapi import Request

logger = logging.getLogger(__name__)


def _append_legacy_auth_cookie_headers(
    response: Response,
    *,
    access: str | None,
    refresh: str | None,
    session_id: str | None,
    request: "Request",
) -> None:
    """Append legacy cookie names (access_token, refresh_token, __session) with config flags.

    Keeps unit-level web.set_auth_cookies canonical-only, while endpoints provide
    compatibility for tests/clients expecting legacy names.

    Controlled by AUTH_LEGACY_COOKIE_NAMES environment variable.
    """
    # Check if legacy cookie names are enabled
    if os.getenv("AUTH_LEGACY_COOKIE_NAMES", "0").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return  # Skip writing legacy cookies

    try:
        from ..cookie_config import format_cookie_header, get_cookie_config

        cfg = get_cookie_config(request)
        ss = str(cfg.get("samesite", "lax")).capitalize()
        dom = cfg.get("domain")
        path = cfg.get("path", "/")
        sec = bool(cfg.get("secure", True))
        if access:
            response.headers.append(
                "set-cookie",
                format_cookie_header(
                    "access_token",
                    access,
                    max_age=int(cfg.get("access_ttl", 1800)),
                    secure=sec,
                    samesite=ss,
                    path=path,
                    httponly=True,
                    domain=dom,
                ),
            )
        if refresh:
            response.headers.append(
                "set-cookie",
                format_cookie_header(
                    "refresh_token",
                    refresh,
                    max_age=int(cfg.get("refresh_ttl", 86400)),
                    secure=sec,
                    samesite=ss,
                    path=path,
                    httponly=True,
                    domain=dom,
                ),
            )
        if session_id:
            response.headers.append(
                "set-cookie",
                format_cookie_header(
                    "__session",
                    session_id,
                    max_age=int(cfg.get("access_ttl", 1800)),
                    secure=sec,
                    samesite=ss,
                    path=path,
                    httponly=True,
                    domain=dom,
                ),
            )
    except ImportError as e:
        logger.warning(f"Failed to import cookie configuration modules: {e}")
    except (ValueError, TypeError) as e:
        logger.warning(f"Invalid cookie configuration values: {e}")
    except Exception as e:
        logger.error(
            f"Unexpected error setting legacy cookie headers: {type(e).__name__}: {e}"
        )


def set_all_auth_cookies(
    response: Response,
    request: "Request",
    *,
    access: str | None,
    refresh: str | None,
    session_id: str | None,
    access_ttl: int,
    refresh_ttl: int,
    append_legacy: bool = True,
    ensure_device_cookie: bool = True,
) -> None:
    """Set canonical cookies via web facade, append legacy if configured, and optionally ensure device cookie.

    Centralizes combined use of app.web.cookies and app.cookies to avoid circular imports in endpoints.
    """
    from ..web.cookies import set_auth_cookies as _set_auth

    _set_auth_cookies_kwargs = dict(
        access=access,
        refresh=refresh,
        session_id=session_id,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=request,
    )
    _set_auth(response, **_set_auth_cookies_kwargs)

    if append_legacy:
        _append_legacy_auth_cookie_headers(
            response,
            access=access,
            refresh=refresh,
            session_id=session_id,
            request=request,
        )

    if ensure_device_cookie:
        try:
            if not getattr(request, "cookies", {}).get("device_id"):
                from ..cookies import set_device_cookie

                set_device_cookie(
                    response,
                    value=os.getenv("DEVICE_COOKIE_SEED")
                    or f"{random.getrandbits(64):016x}",
                    ttl=365 * 24 * 3600,
                    request=request,
                    cookie_name="device_id",
                )
        except Exception:
            # Best-effort device cookie
            pass


def sync_present_tokens_to_cookies(
    response: Response,
    request: "Request",
    *,
    access: str | None,
    refresh: str | None,
    session_id: str | None,
    access_ttl: int,
    refresh_ttl: int,
) -> None:
    """Synchronize existing access/refresh tokens back into cookies without rotation.

    Handles all combinations (both present, access only, refresh only) and appends legacy names.
    """
    try:
        from ..web.cookies import NAMES as _CN
        from ..web.cookies import set_auth_cookies as _set_c
        from ..web.cookies import set_named_cookie as _set_named

        if access and refresh:
            _set_c(
                response,
                access=access,
                refresh=refresh,
                session_id=session_id,
                access_ttl=access_ttl,
                refresh_ttl=refresh_ttl,
                request=request,
            )
            _append_legacy_auth_cookie_headers(
                response,
                access=access,
                refresh=refresh,
                session_id=session_id,
                request=request,
            )
        elif access:
            _set_c(
                response,
                access=access,
                refresh=None,
                session_id=session_id,
                access_ttl=access_ttl,
                refresh_ttl=0,
                request=request,
            )
            _append_legacy_auth_cookie_headers(
                response,
                access=access,
                refresh=None,
                session_id=session_id,
                request=request,
            )
        elif refresh:
            _set_named(
                resp=response,
                name=_CN.refresh,
                value=refresh,
                ttl=refresh_ttl,
                httponly=True,
            )
            _append_legacy_auth_cookie_headers(
                response,
                access=None,
                refresh=refresh,
                session_id=None,
                request=request,
            )
    except Exception:
        # Best-effort; do not raise
        pass


def clear_all_auth_cookies(response: Response, request: "Request") -> None:
    """Clear auth cookies via core helper and web facade; also clear device cookie.

    Centralizes combined use to avoid circular imports in endpoints.
    """
    try:
        from ..cookies import clear_auth_cookies as _clear_core
        from ..cookies import clear_device_cookie

        _clear_core(response, request)
        clear_device_cookie(response, request, cookie_name="device_id")
        try:
            from ..web.cookies import clear_auth_cookies as _web_clear

            _web_clear(response, request)
        except Exception:
            pass
    except Exception:
        # Fallback to core clear only
        try:
            from ..cookies import clear_auth_cookies as _clear_core_only

            _clear_core_only(response, request)
        except Exception:
            pass
