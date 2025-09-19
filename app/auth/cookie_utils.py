"""Cookie utilities for GesahniV2 authentication."""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import secrets
import time
from typing import TYPE_CHECKING, Any

from fastapi import Response

from app.session_store import new_session_id

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


def _truncate_ip(ip: str) -> str:
    if not ip:
        return ""
    try:
        addr = ipaddress.ip_address(ip)
        ip_str = addr.exploded
        if isinstance(addr, ipaddress.IPv4Address):
            return ".".join(ip_str.split(".")[:3])
        return ":".join(ip_str.split(":")[:4])
    except Exception:
        return ""


def _fingerprint_request(request: "Request | None") -> dict[str, str]:
    if request is None:
        return {"ua_hash": "", "ip_hash": "", "device_id": "", "version": 2}

    try:
        user_agent = request.headers.get("user-agent", "")
    except Exception:
        user_agent = ""
    try:
        client_ip = request.client.host if request.client else ""
    except Exception:
        client_ip = ""
    try:
        device_id = request.cookies.get("device_id") if request.cookies else ""
    except Exception:
        device_id = ""

    def _hash(value: str) -> str:
        if not value:
            return ""
        try:
            return hashlib.sha256(value.encode("utf-8")).hexdigest()
        except Exception:
            return ""

    ip_scope = _truncate_ip(client_ip)

    return {
        "ua_hash": _hash(user_agent)[:32],
        "ip_hash": _hash(ip_scope)[:32] if ip_scope else "",
        "device_id": device_id or "",
        "version": 2,
    }


def rotate_session_id(
    response: Response,
    request: "Request",
    *,
    user_id: str | None = None,
    access_token: str | None = None,
    access_payload: dict[str, Any] | None = None,
    access_expires_at: int | None = None,
) -> str:
    """Rotate the opaque session id and bind it to user + device fingerprint."""

    from app.session_store import SessionStoreUnavailable, get_session_store
    from app.web.cookies import read_session_cookie

    payload = access_payload or {}
    exp = access_expires_at
    jti: str | None = None

    if access_token and not payload:
        try:
            from app.tokens import decode_jwt_token

            payload = decode_jwt_token(access_token) or {}
        except Exception:
            payload = {}

    if payload:
        jti = str(payload.get("jti") or "") or None
        exp = exp or payload.get("exp")
        if not user_id:
            candidate = payload.get("user_id") or payload.get("sub")
            user_id = str(candidate) if candidate else user_id

    fingerprint = _fingerprint_request(request)
    now = int(time.time())

    if not exp:
        try:
            from app.cookie_config import get_token_ttls

            access_ttl, _ = get_token_ttls()
        except Exception:
            access_ttl = 1800
        exp = now + max(int(access_ttl), 60)

    exp_int = int(exp)
    jti = jti or secrets.token_hex(16)

    store = get_session_store()

    prior_session_id = None
    try:
        prior_session_id = read_session_cookie(request)
    except Exception:
        prior_session_id = None

    if prior_session_id:
        try:
            store.delete_session(prior_session_id)
        except SessionStoreUnavailable:
            pass
        except Exception:
            pass

    identity: dict[str, Any] = {}
    if payload:
        identity.update({k: v for k, v in payload.items() if isinstance(k, str)})
    if user_id:
        identity["user_id"] = user_id
        identity.setdefault("sub", user_id)
    identity["jti"] = jti
    identity.setdefault("exp", exp_int)
    identity["fingerprint"] = {
        "ua_hash": fingerprint.get("ua_hash", ""),
        "ip_hash": fingerprint.get("ip_hash", ""),
        "device_id": fingerprint.get("device_id", ""),
        "version": fingerprint.get("version", 2),
    }

    try:
        session_id = store.create_session(
            jti,
            exp_int,
            identity=identity,
        )
    except SessionStoreUnavailable:
        session_id = new_session_id()
    except Exception:
        session_id = new_session_id()

    # Ensure identity is persisted even when create_session fell back to legacy mode
    try:
        store.set_session_identity(session_id, identity, exp_int)
    except SessionStoreUnavailable:
        logger.debug(
            "session_store.unavailable:set_identity",
            extra={"meta": {"session_id": session_id}},
        )
    except Exception as exc:
        logger.debug(
            "session_store.error:set_identity",
            extra={
                "meta": {
                    "session_id": session_id,
                    "error": str(exc),
                }
            },
        )

    try:
        request.state.session_id = session_id  # type: ignore[attr-defined]
    except Exception:
        pass

    try:
        response.headers["X-Session-Rotated"] = "true"
    except Exception:
        pass

    return session_id


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
                    or secrets.token_hex(16),
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
