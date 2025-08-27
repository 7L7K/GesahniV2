"""
Google OAuth login URL endpoint.

This module provides a stateless endpoint that generates Google OAuth URLs
and sets short-lived CSRF state cookies for security.
"""

import hashlib
import hmac
import logging
import os
import random
import secrets
import time
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import cookie_config as cookie_cfg
from ..integrations.google.config import JWT_STATE_SECRET
from ..logging_config import req_id_var
from ..security import _jwt_decode

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


# Simple in-memory monitor for OAuth callback failures and clock skew alerts
from collections import deque


class OAuthCallbackMonitor:
    def __init__(self, window_seconds: float = 60.0):
        self.window = float(window_seconds)
        self.total = deque()
        self.failures = deque()

    def record(self, success: bool, ts: float | None = None) -> None:
        now = ts if ts is not None else time.time()
        cutoff = now - self.window
        self.total.append(now)
        if not success:
            self.failures.append(now)
        # prune
        while self.total and self.total[0] < cutoff:
            self.total.popleft()
        while self.failures and self.failures[0] < cutoff:
            self.failures.popleft()

    def failure_rate(self) -> float:
        t = len(self.total)
        if t == 0:
            return 0.0
        return len(self.failures) / t


_oauth_callback_monitor = OAuthCallbackMonitor(
    window_seconds=float(os.getenv("OAUTH_CALLBACK_MONITOR_WINDOW_SECONDS", "60"))
)
_oauth_callback_fail_rate_threshold = float(
    os.getenv("OAUTH_CALLBACK_FAIL_RATE_THRESHOLD", "0.05")
)
_oauth_clock_skew_ms_threshold = float(
    os.getenv("OAUTH_CLOCK_SKEW_MS_THRESHOLD", "2000")
)


def _log_request_summary(
    request: Request, status_code: int, duration_ms: float, **meta
):
    """Log request summary with structured metadata."""
    logger.info(
        f"Request summary: {request.method} {request.url.path} -> {status_code} ({duration_ms:.1f}ms)",
        extra={
            "meta": {
                "req_id": req_id_var.get(),
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                **meta,
            }
        },
    )


def _log_auth_context(
    request: Request, user_id: str = None, is_authenticated: bool = False
):
    """Log authentication context if available."""
    if user_id or is_authenticated:
        logger.info(
            "Auth context available",
            extra={
                "meta": {
                    "req_id": req_id_var.get(),
                    "user_id": user_id,
                    "is_authenticated": is_authenticated,
                }
            },
        )


def _log_route_meta(request: Request, **meta):
    """Log route-specific metadata."""
    logger.info(
        f"Route meta: {request.url.path}",
        extra={"meta": {"req_id": req_id_var.get(), "route": request.url.path, **meta}},
    )


def _log_external_call(service: str, status: int, latency_ms: float, **meta):
    """Log external service calls."""
    logger.info(
        f"External call: {service} -> {status} ({latency_ms:.1f}ms)",
        extra={
            "meta": {
                "req_id": req_id_var.get(),
                "http_out": {
                    "service": service,
                    "status": status,
                    "latency_ms": latency_ms,
                },
                **meta,
            }
        },
    )


def _log_error(
    error_class: str, error_detail: str, cause: str = None, exc_info: bool = False
):
    """Log errors with structured information."""
    meta = {
        "req_id": req_id_var.get(),
        "error_class": error_class,
        "error_detail": error_detail,
    }
    if cause:
        meta["cause"] = cause

    if exc_info:
        logger.error(
            f"Error: {error_class}: {error_detail}", exc_info=True, extra={"meta": meta}
        )
    else:
        logger.error(f"Error: {error_class}: {error_detail}", extra={"meta": meta})


def _allow_redirect(url: str) -> bool:
    """Check if redirect URL is allowed based on OAUTH_REDIRECT_ALLOWLIST."""
    allowed = os.getenv("OAUTH_REDIRECT_ALLOWLIST", "").split(",")
    allowed = [u.strip() for u in allowed if u.strip()]
    if not allowed:
        return True
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc.lower()
        return any(host.endswith(a.lower()) for a in allowed)
    except Exception:
        return False


class LoginUrlResponse(BaseModel):
    """Response model for the login URL endpoint."""

    url: str


def _generate_signed_state() -> str:
    """
    Generate a signed state string for CSRF protection.

    Returns:
        str: timestamp:random:sig format (kept short to avoid URL length issues)
    """
    logger.debug("🔐 Generating timestamp for state")
    timestamp = str(int(time.time()))

    logger.debug("🎲 Generating random token for state")
    random_token = secrets.token_urlsafe(16)  # Reduced from 32 to 16 for shorter state

    # Create signature using a dedicated state secret (separate from JWT_SECRET)
    logger.debug("🔏 Creating HMAC signature for state using JWT_STATE_SECRET")
    message = f"{timestamp}:{random_token}".encode()
    sig_key = (
        JWT_STATE_SECRET.encode()
        if isinstance(JWT_STATE_SECRET, str)
        else JWT_STATE_SECRET
    )
    signature = hmac.new(sig_key, message, hashlib.sha256).hexdigest()[:12]

    state = f"{timestamp}:{random_token}:{signature}"
    logger.debug(
        f"✅ State generated: {timestamp}:[random]:[signature] (length: {len(state)})"
    )
    return state


@router.get("/google/auth/login_url")
async def google_login_url(request: Request) -> Response:
    """
    Generate a Google OAuth login URL with CSRF protection.

    Returns a Google OAuth URL and sets a short-lived state cookie
    for CSRF protection. If Google OAuth is not configured, returns 503.
    """
    start_time = time.time()
    req_id = req_id_var.get()

    logger.info(
        "oauth.login_url",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "oauth.login_url",
                "state_set": False,  # Will be set to True when state is generated
                "next": None,  # Will be set from query params
                "cookie_http_only": True,
                "samesite": "Lax",
            }
        },
    )

    try:
        # Read required environment variables
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI")

        # Fail fast if configuration is missing
        if not client_id or not redirect_uri:
            duration = (time.time() - start_time) * 1000
            _log_error(
                "ConfigurationError",
                "Google OAuth not configured",
                "Missing GOOGLE_CLIENT_ID or GOOGLE_REDIRECT_URI",
            )
            _log_request_summary(request, 503, duration, error="config_missing")
            raise HTTPException(
                status_code=503,
                detail="Google OAuth not configured (set GOOGLE_CLIENT_ID and GOOGLE_REDIRECT_URI)",
            )

        # Generate signed state for CSRF protection
        state = _generate_signed_state()

        # Build Google OAuth URL
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }

        # Add optional parameters only if explicitly configured
        hd = os.getenv("GOOGLE_HD")
        if hd and hd.strip():
            params["hd"] = hd.strip()

        login_hint = os.getenv("GOOGLE_LOGIN_HINT")
        if login_hint and login_hint.strip():
            params["login_hint"] = login_hint.strip()

        # Echo through next query param if present and allowed
        next_url = request.query_params.get("next")
        if next_url:
            if not _allow_redirect(next_url):
                logger.warning(
                    "Blocked disallowed redirect URL",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "component": "google_oauth",
                            "msg": "redirect_blocked",
                            "next_url": (
                                next_url[:100] + "..."
                                if len(next_url) > 100
                                else next_url
                            ),
                        }
                    },
                )
                next_url = "/"  # Reset to safe default
            params["redirect_params"] = f"next={next_url}"

        oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        # Create JSON response with state cookie
        response_data = {"url": oauth_url}

        # Set OAuth state cookie using centralized cookie surface
        # Create a Response object to set the cookie
        import json

        from ..cookies import set_oauth_state_cookies

        http_response = Response(
            content=json.dumps(response_data), media_type="application/json"
        )

        # Use centralized cookie surface for OAuth state cookies
        set_oauth_state_cookies(
            resp=http_response,
            state=state,
            next_url=next_url or "/",
            request=request,
            ttl=300,  # 5 minutes
            provider="g",  # Google-specific cookie prefix
        )

        duration = (time.time() - start_time) * 1000

        # Log successful completion with required fields
        logger.info(
            "oauth.login_url",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "oauth.login_url",
                    "state_set": True,
                    "next": next_url or "/",
                    "cookie_http_only": True,
                    "samesite": "Lax",
                }
            },
        )

        _log_request_summary(request, 200, duration)
        return http_response

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        duration = (time.time() - start_time) * 1000
        _log_request_summary(request, 503, duration, error="http_exception")
        raise
    except Exception as e:
        duration = (time.time() - start_time) * 1000
        _log_error(
            type(e).__name__,
            str(e),
            "Unexpected error in login URL generation",
            exc_info=True,
        )
        _log_request_summary(request, 500, duration, error="unexpected_error")
        raise HTTPException(status_code=500, detail="Internal server error")


def _verify_signed_state(state: str) -> bool:
    """
    Verify a signed state string for CSRF protection.

    Args:
        state: State string in timestamp:random:sig format

    Returns:
        bool: True if state is valid and fresh
    """
    try:
        parts = state.split(":")
        if len(parts) != 3:
            return False

        timestamp, random_token, signature = parts

        # Verify timestamp is recent (within 5 minutes)
        state_time = int(timestamp)
        current_time = int(time.time())
        if current_time - state_time > 300:  # 5 minutes
            return False

        # Verify signature using the dedicated state secret
        message = f"{timestamp}:{random_token}".encode()
        sig_key = (
            JWT_STATE_SECRET.encode()
            if isinstance(JWT_STATE_SECRET, str)
            else JWT_STATE_SECRET
        )
        expected_sig = hmac.new(sig_key, message, hashlib.sha256).hexdigest()[:12]

        return signature == expected_sig
    except Exception:
        return False


@router.get("/google/auth/callback")
async def google_callback(request: Request) -> Response:
    """
    Handle Google OAuth callback with strict state validation.

    Validates the signed state parameter and processes the OAuth code.
    Rejects requests with missing, expired, or invalid state.
    Clears the state cookie after validation and proceeds with session logic.
    """
    start_time = time.time()
    req_id = req_id_var.get()

    logger.info(
        "Google OAuth callback endpoint hit",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "callback_request_started",
            }
        },
    )

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    # Log callback parameters
    logger.info(
        "Callback parameters received",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "callback_params",
                "has_code": bool(code),
                "has_state": bool(state),
                "code_length": len(code) if code else 0,
                "state_length": len(state) if state else 0,
            }
        },
    )

    # Sanity checks for cookie presence (cross-site-redirect friendly)
    cookie_header = request.headers.get('cookie')
    logger.info(
        "OAuth callback cookie sanity check",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "callback_cookie_check",
                "hostname": getattr(request.url, 'hostname', None),
                "cookie_header_is_none": cookie_header is None,
                "cookie_header_length": len(cookie_header) if cookie_header else 0,
                "cookie_header_present": bool(cookie_header and len(cookie_header) > 0),
            }
        },
    )

    cookie_config = cookie_cfg.get_cookie_config(request)

    def _error_response(msg: str, status: int = 400) -> Response:
        import json

        resp = Response(
            content=json.dumps({"detail": msg}),
            media_type="application/json",
            status_code=status,
        )
        # Clear OAuth state cookies using centralized surface
        from ..cookies import clear_oauth_state_cookies

        clear_oauth_state_cookies(resp, request, provider="g")
        return resp

    if not code or not state:
        duration = (time.time() - start_time) * 1000
        _log_error(
            "ValidationError",
            "Missing code or state parameter",
            "OAuth callback missing required parameters",
        )
        _log_request_summary(request, 400, duration, error="missing_params")
        return _error_response("missing_code_or_state", status=400)

    # Get state cookie and validate
    state_cookie = request.cookies.get("g_state")

    # For local development, bypass state cookie validation if cookie is missing
    dev_mode = os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}

    logger.info(
        "State cookie validation",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "state_cookie_check",
                "has_state_cookie": bool(state_cookie),
                "dev_mode": dev_mode,
            }
        },
    )

    if not state_cookie and dev_mode:
        logger.warning(
            "Development mode: Bypassing state cookie validation",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "state_cookie_bypassed_dev",
                }
            },
        )
    elif not state_cookie:
        duration = (time.time() - start_time) * 1000
        _log_error(
            "ValidationError",
            "Missing state cookie",
            "OAuth callback missing state cookie",
        )
        _log_request_summary(request, 400, duration, error="missing_state_cookie")
        return _error_response("missing_state_cookie", status=400)

    # Verify state matches cookie exactly (skip in dev mode if no cookie)
    if state_cookie:
        if state != state_cookie:
            duration = (time.time() - start_time) * 1000
            _log_error(
                "ValidationError",
                "State parameter mismatch",
                "OAuth callback state parameter doesn't match cookie",
            )
            _log_request_summary(request, 400, duration, error="state_mismatch")
            return _error_response("state_mismatch", status=400)

        logger.info(
            "State parameter matches cookie",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "state_match_success",
                }
            },
        )

    # Verify signed state is valid and fresh
    # Measure state age and signature validity
    state_valid = _verify_signed_state(state)
    state_age_ms = None
    try:
        # our signed state format was timestamp:random:sig
        parts = state.split(":")
        if parts and parts[0].isdigit():
            ts = int(parts[0])
            state_age_ms = (time.time() - ts) * 1000
    except Exception:
        state_age_ms = None

    logger.info(
        "Signed state validation",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "signed_state_check",
                "state_valid": state_valid,
                "state_age_ms": state_age_ms,
                "dev_mode": dev_mode,
            }
        },
    )

    if not state_valid:
        if dev_mode:
            logger.warning(
                "Development mode: Bypassing signed state validation",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "component": "google_oauth",
                        "msg": "signed_state_bypassed_dev",
                    }
                },
            )
        else:
            duration = (time.time() - start_time) * 1000
            _log_error(
                "ValidationError",
                "Invalid or expired state",
                "OAuth callback state signature invalid or expired",
            )
            _log_request_summary(request, 400, duration, error="invalid_state")
            return _error_response("invalid_state", status=400)

    # State is valid - clear/rotate the state cookie after use
    logger.info(
        "Clearing OAuth state cookies after successful validation",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "state_cookies_cleared",
            }
        },
    )

    # Create response object to set cleared cookie
    response = Response(
        content="OAuth callback received successfully. State validation passed.",
        media_type="text/plain",
    )

    # Clear OAuth state cookies using centralized surface
    from ..cookies import clear_oauth_state_cookies

    clear_oauth_state_cookies(response, request, provider="g")

    # State validation complete - proceed with usual session logic
    logger.info(
        "Google OAuth callback state validated successfully",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "state_validation_complete",
            }
        },
    )

    # Perform token exchange and create an application session/redirect.
    try:
        from urllib.parse import urlencode
        from uuid import uuid4

        from starlette.responses import RedirectResponse

        from ..integrations.google import oauth as go
        from ..integrations.google.db import GoogleToken, SessionLocal, init_db

        # Exchange the authorization code (state already validated by this endpoint)
        logger.info(
            "Starting Google token exchange",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "token_exchange_started",
                }
            },
        )

        # Wrap token exchange with OpenTelemetry span and capture latency
        from ..otel_utils import get_trace_id_hex, start_span

        token_exchange_start = time.time()
        with start_span(
            "google.oauth.token.exchange", {"component": "google_oauth"}
        ) as _span:
            creds = go.exchange_code(code, state, verify_state=False)
            # If span present, set google token latency on span
            try:
                _span.set_attribute("google_token_latency_ms", 0)
            except Exception:
                pass
        token_exchange_duration = (time.time() - token_exchange_start) * 1000
        try:
            if _span is not None and hasattr(_span, "set_attribute"):
                _span.set_attribute(
                    "google_token_latency_ms", int(token_exchange_duration)
                )
        except Exception:
            pass

        # Emit extra telemetry in logs/meta
        try:
            trace_id = get_trace_id_hex()
        except Exception:
            trace_id = None

        # Log external call to Google token exchange
        _log_external_call(
            "google_token",
            200,  # Assume success if no exception
            token_exchange_duration,
            exchange_status="ok",
            trace_id=trace_id,
            google_token_latency_ms=token_exchange_duration,
        )

        # Try to extract email/sub from id_token (best-effort, without verification)
        provider_user_id = None
        email = None
        try:
            id_token = getattr(creds, "id_token", None)
            if id_token:
                claims = _jwt_decode(id_token, options={"verify_signature": False})
                email = claims.get("email") or claims.get("email_address")
                provider_user_id = claims.get("sub") or email
        except Exception as e:
            logger.warning(
                "Failed to decode ID token",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "component": "google_oauth",
                        "msg": "id_token_decode_failed",
                        "error": str(e),
                    }
                },
            )
            provider_user_id = None

        # Fallback identifiers
        if not provider_user_id:
            provider_user_id = (
                getattr(creds, "refresh_token", None)
                or getattr(creds, "token", None)
                or str(uuid4())
            )
        if not email:
            # Use provider_user_id as email fallback (not ideal but deterministic)
            email = str(provider_user_id)

        # Persist provider record into google_oauth DB (best-effort)
        try:
            init_db()
            rec = go.creds_to_record(creds)
            uid = str(email).lower()
            with SessionLocal() as s:
                row = s.get(GoogleToken, uid)
                if row is None:
                    row = GoogleToken(
                        user_id=uid,
                        access_token=rec.get("access_token"),
                        refresh_token=rec.get("refresh_token"),
                        token_uri=rec.get("token_uri"),
                        client_id=rec.get("client_id"),
                        client_secret=rec.get("client_secret"),
                        scopes=rec.get("scopes"),
                        expiry=rec.get("expiry"),
                    )
                    s.add(row)
                else:
                    row.access_token = rec.get("access_token")
                    row.refresh_token = rec.get("refresh_token")
                    row.token_uri = rec.get("token_uri")
                    row.client_id = rec.get("client_id")
                    row.client_secret = rec.get("client_secret")
                    row.scopes = rec.get("scopes")
                    row.expiry = rec.get("expiry")
                s.commit()

            logger.info(
                "Google tokens persisted successfully",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "component": "google_oauth",
                        "msg": "tokens_persisted",
                        "user_id": uid,
                    }
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to persist Google tokens (non-fatal)",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "component": "google_oauth",
                        "msg": "token_persistence_failed",
                        "error": str(e),
                    }
                },
            )

        # Mint application JWTs (access + refresh) for the user and redirect
        app_url = os.getenv("APP_URL", "http://localhost:3000")
        # Use tokens.py facade instead of direct JWT encoding
        from ..tokens import make_access, make_refresh

        at = make_access({"user_id": uid})
        rt = make_refresh({"user_id": uid})

        # Build redirect query - keep it compact and URL-encoded
        q = urlencode({"access_token": at, "refresh_token": rt})

        # If APP_URL appears to point at this backend (common in local dev),
        # prefer the browser origin or referer so the redirect lands on the
        # frontend (e.g. http://localhost:3000) instead of the backend port.
        try:
            from urllib.parse import urlparse

            parsed = urlparse(app_url)
            host_matches_backend = False
            try:
                host_matches_backend = (parsed.hostname == request.url.hostname) and (
                    parsed.port == request.url.port
                )
            except Exception:
                host_matches_backend = False

            if host_matches_backend:
                origin = request.headers.get("origin") or request.headers.get("referer")
                if origin:
                    op = urlparse(origin)
                    app_url = f"{op.scheme}://{op.netloc}"
        except Exception:
            # Best-effort only; fall back to APP_URL env value
            pass

        # Set tokens as HttpOnly cookies and redirect to frontend root
        # Determine final frontend origin similar to earlier logic
        final_root = f"{app_url.rstrip('/')}/"
        try:
            from urllib.parse import urlparse

            parsed = urlparse(app_url)
            host_matches_backend = False
            try:
                host_matches_backend = (parsed.hostname == request.url.hostname) and (
                    parsed.port == request.url.port
                )
            except Exception:
                host_matches_backend = False
            if host_matches_backend:
                origin = request.headers.get("origin") or request.headers.get("referer")
                if origin:
                    op = urlparse(origin)
                    final_root = f"{op.scheme}://{op.netloc}/"
        except Exception:
            pass

        # Decide whether to perform a 302 redirect or return an HTML shim that
        # sets cookies and immediately redirects via JS. The HTML shim can be
        # more reliable for some browsers when Set-Cookie appears on redirect
        # responses.
        use_html_shim = os.getenv("OAUTH_HTML_REDIRECT", "0").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        # Get TTLs from centralized configuration
        access_ttl, refresh_ttl = cookie_cfg.get_token_ttls()

        # Optional legacy __session cookie for integrations
        if use_html_shim:
            # Return an HTML page that immediately navigates to the frontend
            # root via JS. Set cookies on this 200 response so browsers reliably
            # persist them even when redirects might be finicky.
            from starlette.responses import HTMLResponse

            html = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><meta http-equiv=\"x-ua-compatible\" content=\"ie=edge\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
<title>Signing in...</title></head>
<body>
<p>Signing you in… If you are not redirected, <a id=\"link\" href=\"{final_root}\">click here</a>.</p>
<script>window.location.replace({final_root!r});</script>
</body></html>"""

            resp = HTMLResponse(content=html, status_code=200)
        else:
            from starlette.responses import RedirectResponse

            resp = RedirectResponse(url=final_root, status_code=302)

        session_id = None
        if os.getenv("ENABLE_SESSION_COOKIE", "") in ("1", "true", "yes"):
            # Create opaque session ID instead of using JWT
            try:
                from ..auth import _create_session_id

                payload = _jwt_decode(at, os.getenv("JWT_SECRET"), algorithms=["HS256"])
                jti = payload.get("jti")
                expires_at = payload.get("exp", time.time() + access_ttl)
                if jti:
                    session_id = _create_session_id(jti, expires_at)
                else:
                    session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"
            except Exception as e:
                logger.warning(
                    "Failed to create session ID",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "component": "google_oauth",
                            "msg": "session_id_creation_failed",
                            "error": str(e),
                        }
                    },
                )
                session_id = f"sess_{int(time.time())}_{random.getrandbits(32):08x}"

        # Use centralized cookie functions
        from ..cookies import set_auth_cookies

        # Confirm resolved cookie attributes are localhost-safe for dev
        try:
            resolved_ccfg = cookie_cfg.get_cookie_config(request)
            # Log resolved cookie attributes for debugging and verification
            logger.info(
                "Resolved cookie attributes",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "path": resolved_ccfg.get("path"),
                        "samesite": resolved_ccfg.get("samesite"),
                        "secure": resolved_ccfg.get("secure"),
                        "httponly": resolved_ccfg.get("httponly"),
                        "domain": resolved_ccfg.get("domain"),
                    }
                },
            )

            # Emit a warning if attributes look unsafe for localhost development
            if _get_scheme(request) != "https":
                if bool(resolved_ccfg.get("secure")):
                    logger.warning(
                        "Cookie Secure=True on non-HTTPS request; overriding for dev may be required",
                        extra={"meta": {"req_id": req_id}},
                    )
                if str(resolved_ccfg.get("samesite", "")).lower() == "none":
                    logger.warning(
                        "Cookie SameSite=None on non-HTTPS request; this may prevent browsers from storing cookies on localhost",
                        extra={"meta": {"req_id": req_id}},
                    )
        except Exception:
            # Best-effort only; do not fail the flow if cookie config lookup/logging fails
            pass

        # Write cookies using the canonical names
        set_auth_cookies(
            resp,
            access=at,
            refresh=rt,
            session_id=session_id,
            access_ttl=access_ttl,
            refresh_ttl=refresh_ttl,
            request=request,
        )

        # Emit compact cookie-write observability so ops can verify attributes/names at a glance
        try:
            # Report canonical names in logs
            try:
                from ..cookie_names import ACCESS_TOKEN, REFRESH_TOKEN

                cookie_names_written = [ACCESS_TOKEN, REFRESH_TOKEN]
            except Exception:
                cookie_names_written = ["access_token", "refresh_token"]
            # Use previously resolved cookie config when available
            ccfg = (
                resolved_ccfg
                if "resolved_ccfg" in locals()
                else cookie_cfg.get_cookie_config(request)
            )
            samesite_map = {"lax": "Lax", "strict": "Strict", "none": "None"}
            auth_cookie_attrs = {
                "path": ccfg.get("path", "/"),
                "samesite": samesite_map.get(
                    str(ccfg.get("samesite", "lax")).lower(), "Lax"
                ),
                "secure": bool(ccfg.get("secure", False)),
                "http_only": bool(ccfg.get("httponly", True)),
            }
            logger.info(
                "oauth.callback.cookies_written",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "set_auth_cookies": True,
                        "cookie_names_written": cookie_names_written,
                        "auth_cookie_attrs": auth_cookie_attrs,
                        "redirect": final_root,
                    }
                },
            )
        except Exception:
            pass

        duration = (time.time() - start_time) * 1000

        # Log successful completion with required fields and cookie attributes
        try:
            ccfg = cookie_cfg.get_cookie_config(request)
            samesite_map = {"lax": "Lax", "strict": "Strict", "none": "None"}
            auth_cookie_attrs = {
                "path": ccfg.get("path", "/"),
                "samesite": samesite_map.get(
                    str(ccfg.get("samesite", "lax")).lower(), "Lax"
                ),
                "secure": bool(ccfg.get("secure", False)),
                "http_only": bool(ccfg.get("httponly", True)),
            }
        except Exception:
            auth_cookie_attrs = {
                "path": "/",
                "samesite": "Lax",
                "secure": False,
                "http_only": True,
            }

        logger.info(
            "oauth.callback.success",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "oauth.callback.success",
                    "state_valid": state_valid,
                    "token_exchange": "ok",
                    "set_auth_cookies": True,
                    "auth_cookie_attrs": auth_cookie_attrs,
                    "redirect_to": final_root,
                    "redirect": final_root,
                    "google_token_latency_ms": int(token_exchange_duration),
                    "trace_id": trace_id,
                }
            },
        )

        # Record monitor success and emit alert if failure rate threshold exceeded
        try:
            _oauth_callback_monitor.record(success=True)
            rate = _oauth_callback_monitor.failure_rate()
            if rate > _oauth_callback_fail_rate_threshold:
                logger.warning(
                    "oauth.callback.fail_rate_high", extra={"meta": {"fail_rate": rate}}
                )
        except Exception:
            pass

        # Log auth context
        _log_auth_context(request, user_id=uid, is_authenticated=True)

        _log_request_summary(request, 302, duration)
        return resp

    except HTTPException as e:
        duration = (time.time() - start_time) * 1000

        # Log the HTTP exception
        _log_error(
            type(e).__name__, str(e), "OAuth callback HTTP exception", exc_info=False
        )

        # Log first 200 chars of Google's response body if available (DEBUG only)
        try:
            if hasattr(e, "response") and hasattr(e.response, "text"):
                response_body = e.response.text[:200]
                logger.debug(
                    "Google response body (first 200 chars)",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "component": "google_oauth",
                            "msg": "google_response_body",
                            "response_body": response_body,
                        }
                    },
                )
        except Exception:
            # Ignore errors in logging response body
            pass

        # Log callback failure with structured reason code
        reason_code = (
            getattr(e, "detail", "oauth_exchange_failed") or "oauth_exchange_failed"
        )
        logger.warning(
            "oauth.callback.fail",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "oauth.callback.fail",
                    "state_valid": state_valid if "state_valid" in locals() else False,
                    "token_exchange": "fail",
                    "google_status": e.status_code,
                    "reason": reason_code,
                    "redirect": f"/login?err={reason_code}",
                }
            },
        )

        try:
            _oauth_callback_monitor.record(success=False)
            rate = _oauth_callback_monitor.failure_rate()
            if rate > _oauth_callback_fail_rate_threshold:
                logger.warning(
                    "oauth.callback.fail_rate_high", extra={"meta": {"fail_rate": rate}}
                )
        except Exception:
            pass

        _log_request_summary(request, e.status_code, duration, error="http_exception")
        return _error_response(e.detail, status=e.status_code)

    except Exception as e:
        duration = (time.time() - start_time) * 1000

        # Log the exception type/message (always)
        _log_error(
            type(e).__name__, str(e), "OAuth callback processing failed", exc_info=True
        )

        # Log first 200 chars of Google's response body if available (DEBUG only)
        try:
            if hasattr(e, "response") and hasattr(e.response, "text"):
                response_body = e.response.text[:200]
                logger.debug(
                    "Google response body (first 200 chars)",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "component": "google_oauth",
                            "msg": "google_response_body",
                            "response_body": response_body,
                        }
                    },
                )
        except Exception:
            # Ignore errors in logging response body
            pass

        # Determine user-friendly message and status
        msg = "oauth_callback_failed"
        status = 500
        try:
            if isinstance(e, ValueError) and "JWT_SECRET" in str(e):
                msg = "server_misconfigured_jwt_secret"
                status = 503
        except Exception:
            pass

        # Log callback failure with required fields
        # Emit error with structured reason code
        reason_code = "oauth_exchange_failed"
        logger.error(
            "oauth.callback.fail",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "oauth.callback.fail",
                    "state_valid": state_valid if "state_valid" in locals() else False,
                    "token_exchange": "fail",
                    "google_status": status,
                    "reason": reason_code,
                    "redirect": f"/login?err={reason_code}",
                }
            },
        )

        try:
            _oauth_callback_monitor.record(success=False)
            rate = _oauth_callback_monitor.failure_rate()
            if rate > _oauth_callback_fail_rate_threshold:
                logger.warning(
                    "oauth.callback.fail_rate_high", extra={"meta": {"fail_rate": rate}}
                )
        except Exception:
            pass

        # If running locally, return trace in the HTTP response for quick debugging.
        # WARNING: do NOT enable this in production.
        if os.getenv("ENV", "").lower() in ("dev", "development", "local", "test"):
            return _error_response(f"{msg}: {type(e).__name__}: {e}", status=status)

        # Otherwise, return sanitized cookie-clearing response (no internals leaked)
        _log_request_summary(request, status, duration, error="callback_failed")
        return _error_response(msg, status=status)


# Note: This endpoint is stateless - no database writes.
# The cookie is just to bind browser↔callback for CSRF protection.
# If misconfigured, it fails fast with 503 (no silent defaults).
