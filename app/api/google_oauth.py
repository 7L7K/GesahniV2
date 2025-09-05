"""
Google OAuth login URL endpoint.

This module provides a stateless endpoint that generates Google OAuth URLs
and sets short-lived CSRF state cookies for security.

ALERTING THRESHOLDS:
- google_token_exchange_failed_total > 2/min (5m window) → PAGE
- google_refresh_failure_total > 1% of refresh attempts (15m window) → WARN
- provider_sub_mismatch (ever) → WARN
"""

import hashlib
import hmac
import inspect
import logging
import os
import random
import secrets
import time
import base64
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import cookie_config as cookie_cfg
from ..integrations.google.config import JWT_STATE_SECRET
from ..integrations.google.state import generate_signed_state, verify_signed_state, generate_pkce_verifier, generate_pkce_challenge
from ..logging_config import req_id_var
from ..security import jwt_decode
from ..error_envelope import raise_enveloped

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])


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
        from urllib.parse import urlparse, unquote

        # URL-decode the URL multiple times to handle nested encoding
        decoded_url = url
        for _ in range(5):  # Decode up to 5 levels deep
            previous = decoded_url
            decoded_url = unquote(decoded_url)
            if decoded_url == previous:  # No more encoding layers
                break

        host = urlparse(decoded_url).netloc.lower()
        return any(host.endswith(a.lower()) for a in allowed)
    except Exception:
        return False


class LoginUrlResponse(BaseModel):
    """Response model for the login URL endpoint."""

    url: str





@router.get("/auth/login_url")
async def google_login_url(request: Request) -> Response:
    """
    Generate a Google OAuth login URL with CSRF protection.

    Returns a Google OAuth URL and sets a short-lived state cookie
    for CSRF protection. If Google OAuth is not configured, returns 503.
    """
    start_time = time.time()
    req_id = req_id_var.get()

    logger.info(
        "OAUTH_DEBUG: Login URL endpoint called",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "oauth.login_url",
                "endpoint": "/auth/google/login_url",
                "state_set": False,  # Will be set to True when state is generated
                "next": None,  # Will be set from query params
                "cookie_http_only": True,
                "samesite": "Lax",
                "user_agent": request.headers.get("user-agent", "unknown"),
                "referer": request.headers.get("referer", "unknown"),
            }
        },
    )

    try:
        # Read required environment variables (could also import from integration config)
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
            raise HTTPException(status_code=503, detail="Google OAuth not configured")

        # Generate signed state for CSRF protection
        state = generate_signed_state()

        # Generate PKCE parameters for enhanced security
        code_verifier = generate_pkce_verifier()
        code_challenge = generate_pkce_challenge(code_verifier)

        # Log PKCE setup for debugging
        logger.info(
            "google_oauth_login",
            extra={"meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "has_pkce": bool(code_verifier),
                "method": "S256",
                "state": state[:16] + "..." if len(state) > 16 else state
            }}
        )

        # Build Google OAuth URL with proper scopes from integration config
        from ..integrations.google.config import get_google_scopes
        scopes = get_google_scopes()
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
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
                            "next_url_length": len(next_url) if next_url else 0,
                        }
                    },
                )
                next_url = "/"  # Reset to safe default
            params["redirect_params"] = f"next={next_url}"

        oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"

        # Create JSON response with state cookie
        response_data = {"auth_url": oauth_url}

        # Set OAuth state cookie using centralized cookie surface
        # Create a Response object to set the cookie
        import json

        from ..web.cookies import set_oauth_state_cookies

        http_response = Response(
            content=json.dumps(response_data), media_type="application/json"
        )

        # Use centralized cookie surface for OAuth state cookies
        from ..cookies import read_session_cookie

        current_session = read_session_cookie(request)

        set_oauth_state_cookies(
            resp=http_response,
            state=state,
            next_url=next_url or "/",
            request=request,
            ttl=300,  # 5 minutes
            provider="g",  # Google-specific cookie prefix
            code_verifier=code_verifier,  # Store PKCE verifier for callback
            session_id=current_session,
        )

        duration = (time.time() - start_time) * 1000

        # Log successful completion with required fields (no previews)
        logger.info(
            "oauth.login_url",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "oauth.login_url",
                    "state_set": True,
                    "next_length": len(next_url) if next_url else 0,
                    "cookie_http_only": True,
                    "samesite": "Lax",
                }
            },
        )

        # Emit GOOGLE_CONNECT_STARTED metric
        try:
            from ..metrics import GOOGLE_CONNECT_STARTED
            import hashlib
            scopes_hash = hashlib.sha256(" ".join(sorted(scopes)).encode()).hexdigest()[:8]
            GOOGLE_CONNECT_STARTED.labels(user_id="unknown", scopes_hash=scopes_hash).inc()
        except Exception:
            pass

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
        from ..error_envelope import raise_enveloped

        raise_enveloped("internal", "internal server error", hint="try again shortly", status=500)





@router.get("/auth/callback")
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
        "OAUTH_DEBUG: Google OAuth callback endpoint hit",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "callback_request_started",
                "endpoint": "/auth/google/callback",
                "user_agent": request.headers.get("user-agent", "unknown"),
                "referer": request.headers.get("referer", "unknown"),
                "origin": request.headers.get("origin", "unknown"),
                "full_url": str(request.url),
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

    # Get PKCE code verifier from cookie
    code_verifier_cookie = request.cookies.get("g_code_verifier")

    # For local development, bypass validations if cookie is missing
    dev_mode = os.getenv("DEV_MODE", "0").lower() in {"1", "true", "yes", "on"}

    # Enforce presence of PKCE verifier for security (bypass in dev mode for testing)
    if not code_verifier_cookie and not dev_mode:
        duration = (time.time() - start_time) * 1000
        _log_error(
            "ValidationError",
            "Missing PKCE code verifier",
            "OAuth callback missing PKCE verifier",
        )
        _log_request_summary(request, 400, duration, error="missing_verifier")
        return _error_response("missing_verifier", status=400)
    elif not code_verifier_cookie and dev_mode:
        logger.warning(
            "Development mode: Bypassing PKCE verifier validation",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "pkce_verifier_bypassed_dev",
                }
            },
        )
        # Use a dummy verifier for dev mode
        code_verifier_cookie = "dev_mode_dummy_verifier" * 3  # 75 chars to meet length requirement

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

    # Verify state matches cookie exactly (skip in dev mode)
    if state_cookie and not dev_mode:
        if state != state_cookie:
            duration = (time.time() - start_time) * 1000
            _log_error(
                "ValidationError",
                "State parameter mismatch",
                "OAuth callback state parameter doesn't match cookie",
            )
            _log_request_summary(request, 400, duration, error="state_mismatch")
            return _error_response("state_mismatch", status=400)
    elif state_cookie and dev_mode and state != state_cookie:
        logger.warning(
            "Development mode: State mismatch detected but proceeding",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "state_mismatch_bypassed_dev",
                    "expected": state_cookie,
                    "received": state,
                }
            },
        )

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
    try:
        # verify_signed_state will consume the nonce on success and raise
        # NonceConsumedError if the nonce was already consumed.
        from ..integrations.google.state import NonceConsumedError

        try:
            state_valid = verify_signed_state(state, consume_nonce_on_success=True)
            nonce_consumed = False
        except NonceConsumedError:
            state_valid = False
            nonce_consumed = True
    except Exception:
        state_valid = False
        nonce_consumed = False

    state_age_ms = None
    try:
        # our signed state format is timestamp:random:nonce:sig
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
                "nonce_consumed": nonce_consumed,
                "state_age_ms": state_age_ms,
                "dev_mode": dev_mode,
            }
        },
    )

    if not state_valid:
        if nonce_consumed:
            # Nonce already used - return 409 Conflict
            duration = (time.time() - start_time) * 1000
            _log_error(
                "ValidationError",
                "State nonce already consumed",
                "OAuth callback state nonce already used (anti-replay protection)",
            )
            _log_request_summary(request, 409, duration, error="nonce_already_used")
            return _error_response("state_already_used", status=409)
        elif dev_mode:
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

    # Mark cookies for clearing (actual clearing will be applied to final response)
    logger.info(
        "Preparing to clear OAuth state cookies after validation",
        extra={
            "meta": {
                "req_id": req_id,
                "component": "google_oauth",
                "msg": "state_cookies_prepare_clear",
            }
        },
    )

    # Log callback start with state and verifier status (put custom fields into `extra`)
    logger.info(
        "google_oauth_cb_start",
        extra={
            "meta": {"req_id": req_id, "component": "google_oauth"},
            "state_ok": state_valid,
            "has_verifier": bool(code_verifier_cookie),
        },
    )

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

        # Enforce state -> session binding to prevent cross-tab CSRF/status races.
    try:
        from ..cookies import read_session_cookie

        provider_session = request.cookies.get("g_session")
        current_session = read_session_cookie(request)
        if provider_session and current_session and provider_session != current_session:
            duration = (time.time() - start_time) * 1000
            _log_error(
                "ValidationError",
                "OAuth state session mismatch",
                "OAuth state session id does not match current session",
            )
            _log_request_summary(request, 409, duration, error="state_session_mismatch")
            return _error_response("state_session_mismatch", status=409)
    except Exception:
        # Best-effort only; do not fail login if session binding check errors
        pass

    # After identity resolution, ensure handoff invariant: if an authenticated
    # cookie user exists and does not match the callback's canonical user, log
    # a security event and force session rotation.

    # Initialize variables for early logging
    uid = None
    provider_sub = None
    provider_iss = None

    try:
        from ..deps.user import get_current_user_id

        try:
            existing_cookie_user = get_current_user_id(request=request)
        except Exception:
            existing_cookie_user = "anon"

        if existing_cookie_user and existing_cookie_user != "anon" and existing_cookie_user != uid:
            # Log invariant violation
            logger.warning(
                "SEC_IDENTITY_HANDOFF_MISMATCH",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "existing_cookie_user": existing_cookie_user,
                        "callback_user": uid,
                        "provider_sub": provider_sub,
                        "provider_iss": provider_iss,
                    }
                },
            )
            # Force session deletion for safety (rotation will occur on cookie write)
            try:
                from ..cookies import read_session_cookie
                from ..auth import _delete_session_id

                old_sess = read_session_cookie(request)
                if old_sess:
                    _delete_session_id(old_sess)
            except Exception:
                pass
    except Exception:
        pass

    # Perform token exchange and create an application session/redirect.
    try:
        from urllib.parse import urlencode
        from uuid import uuid4

        from starlette.responses import RedirectResponse

        from ..integrations.google import oauth as go
        from ..integrations.google.db import GoogleToken, SessionLocal, init_db

        # Exchange the authorization code (state already validated by this endpoint)
        logger.info(
            "OAUTH_DEBUG: Starting Google token exchange",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "token_exchange_started",
                    "has_code": bool(code),
                    "has_code_verifier": bool(code_verifier_cookie),
                    "code_length": len(code) if code else 0,
                    "code_verifier_length": len(code_verifier_cookie) if code_verifier_cookie else 0,
                }
            },
        )

        # Wrap token exchange with OpenTelemetry span and capture latency
        from ..otel_utils import get_trace_id_hex, start_span

        token_exchange_start = time.time()
        with start_span(
            "google.oauth.token.exchange", {"component": "google_oauth"}
        ) as _span:
            try:
                # Support both sync and async exchange_code implementations / mocks.
                import inspect

                maybe = go.exchange_code(code, state, verify_state=False, code_verifier=code_verifier_cookie)
                if inspect.isawaitable(maybe):
                    creds = await maybe
                else:
                    creds = maybe
            except Exception as e:
                # Integration layer emits metrics and raises OAuthError for sanitized issues.
                from ..integrations.google.errors import OAuthError as _OAuthError

                if isinstance(e, _OAuthError):
                    # Use global HTTPException imported at module top
                    raise HTTPException(status_code=e.http_status, detail=e.as_response())
                # Unknown errors -> generic 500
                raise HTTPException(status_code=500, detail="oauth_exchange_failed")
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

        # Prefer frontend redirect target from cookie if present/allowed
        try:
            next_cookie = request.cookies.get("g_next")
        except Exception:
            next_cookie = None

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

        # Try to extract iss/sub/email from id_token (best-effort, without verification)
        provider_sub = None
        provider_iss = None
        email = None

        # Log what Google actually returned in the credentials
        creds_id_token = getattr(creds, "id_token", None)
        logger.info(
            "Google OAuth credentials received",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "google_credentials_received",
                    "has_id_token": creds_id_token is not None,
                    "id_token_length": len(creds_id_token or ""),
                    "creds_type": type(creds).__name__,
                    "creds_attributes": list(vars(creds).keys()) if hasattr(creds, '__dict__') else 'no_attrs',
                }
            },
        )

        try:
            id_token = getattr(creds, "id_token", None)
            if id_token:
                claims = jwt_decode(id_token, options={"verify_signature": False})
                email = claims.get("email") or claims.get("email_address")
                provider_sub = claims.get("sub") or None
                provider_iss = claims.get("iss") or None

                # Fallback for Google OAuth: if iss is missing, use standard Google issuer
                if not provider_iss and provider_sub:
                    # This is likely a Google OAuth token if we have a sub but no iss
                    provider_iss = "https://accounts.google.com"
                    logger.info(
                        "Applied Google OAuth issuer fallback",
                        extra={
                            "meta": {
                                "req_id": req_id,
                                "component": "google_oauth",
                                "msg": "issuer_fallback_applied",
                                "provider_sub": provider_sub,
                                "fallback_issuer": provider_iss,
                            }
                        },
                    )
        except Exception as e:
            logger.warning(
                "Failed to decode ID token",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "component": "google_oauth",
                        "msg": "id_token_decode_failed",
                        "error": str(e),
                        "has_id_token": id_token is not None,
                        "id_token_length": len(id_token) if id_token else 0,
                    }
                },
            )

        # Log extracted values for debugging
        logger.info(
            "Google OAuth token extraction results",
            extra={
                "meta": {
                    "req_id": req_id,
                    "component": "google_oauth",
                    "msg": "token_extraction_results",
                    "has_provider_iss": provider_iss is not None,
                    "has_provider_sub": provider_sub is not None,
                    "has_email": email is not None,
                    "provider_iss": provider_iss,
                    "provider_sub_length": len(provider_sub) if provider_sub else 0,
                }
            },
        )

        # Fallback identifiers
        if not provider_sub:
            provider_sub = None
        if not email:
            # Use provider_sub as email fallback (not ideal but deterministic)
            email = str(provider_sub or uuid4())

        # Determine canonical application user via deterministic identity linking
        try:
            from .. import cookies as cookie_helpers
            from .. import auth_store as auth_store
            import secrets as _secrets

            # Look up existing identity by provider+sub
            canonical_user = None
            identity_id_used = None
            if provider_sub:
                try:
                    ident = await auth_store.get_oauth_identity_by_provider("google", provider_iss, str(provider_sub))
                except Exception:
                    ident = None
                if ident and ident.get("user_id"):
                    identity_id_used = ident.get("id")
                    canonical_user = ident.get("user_id")

            # If no identity, try to locate existing user by email
            if not canonical_user:
                if email:
                    existing_user = await auth_store.get_user_by_email(email)
                else:
                    existing_user = None

                if existing_user:
                    # If provider reports email_verified, link identity immediately
                    if bool(claims.get("email_verified", False)):
                        new_id = f"g_{_secrets.token_hex(8)}"
                        try:
                            await auth_store.link_oauth_identity(
                                id=new_id,
                                user_id=existing_user["id"],
                                provider="google",
                                provider_iss=provider_iss,
                                provider_sub=str(provider_sub),
                                email_normalized=email or "",
                            )
                            canonical_user = existing_user["id"]
                            identity_id_used = new_id
                        except Exception as e:
                            # Check if this is a unique constraint violation (race condition)
                            # Only catch the specific case where another process inserted the same identity
                            if "UNIQUE constraint failed" in str(e) or "constraint failed" in str(e):
                                # Race condition: another process inserted the identity concurrently
                                # Re-select to recover the existing identity instead of failing
                                try:
                                    existing_ident = await auth_store.get_oauth_identity_by_provider("google", provider_iss, str(provider_sub))
                                    if existing_ident:
                                        identity_id_used = existing_ident.get("id")
                                        canonical_user = existing_ident.get("user_id")
                                    else:
                                        # Cannot determine identity -> fail fast
                                        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                                        return RedirectResponse(f"{frontend_url}/settings#google?google_error=identity_link_failed", status_code=303)
                                except Exception:
                                    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                                    return RedirectResponse(f"{frontend_url}/settings#google?google_error=identity_link_failed", status_code=303)
                            else:
                                # Not a race condition - re-raise the original exception
                                raise
                    else:
                        # Email not verified: require user verify their email first
                        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                        return RedirectResponse(f"{frontend_url}/settings#google?google_error=email_unverified", status_code=303)
                else:
                    # No existing user: create one and link identity
                    try:
                        new_user_id = f"user_{_secrets.token_hex(8)}"
                        await auth_store.create_user(id=new_user_id, email=email or str(provider_sub), name=None)
                        new_id = f"g_{_secrets.token_hex(8)}"
                        try:
                            await auth_store.link_oauth_identity(
                                id=new_id,
                                user_id=new_user_id,
                                provider="google",
                                provider_iss=provider_iss,
                                provider_sub=str(provider_sub),
                                email_normalized=email or "",
                            )
                            canonical_user = new_user_id
                            identity_id_used = new_id
                        except Exception as e:
                            # Check if this is a unique constraint violation (race condition)
                            # Only catch the specific case where another process inserted the same identity
                            if "UNIQUE constraint failed" in str(e) or "constraint failed" in str(e):
                                # Race condition: another process inserted the identity concurrently
                                # Re-select to recover the existing identity instead of failing
                                try:
                                    existing_ident = await auth_store.get_oauth_identity_by_provider("google", provider_iss, str(provider_sub))
                                    if existing_ident:
                                        identity_id_used = existing_ident.get("id")
                                        canonical_user = existing_ident.get("user_id")
                                    else:
                                        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                                        return RedirectResponse(f"{frontend_url}/settings#google?google_error=identity_link_failed", status_code=303)
                                except Exception:
                                    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                                    return RedirectResponse(f"{frontend_url}/settings#google?google_error=identity_link_failed", status_code=303)
                            else:
                                # Not a race condition - re-raise the original exception
                                raise
                    except Exception:
                        canonical_user = str(email).lower()

            uid = canonical_user or str(email).lower()

        except Exception:
            # Fallback behavior: use email as uid (legacy)
            uid = str(email).lower()

        # Persist provider record into google_oauth DB (best-effort)
        try:
            init_db()
            rec = go.creds_to_record(creds)
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

        # Guardrails: ensure provider_iss is present. If id_token didn't include
        # iss, try to reuse an existing valid row's provider_iss for this user/sub.
        try:
            from ..auth_store_tokens import get_token as _get_token

            # If provider_iss missing, attempt to reuse from existing DB row
            if not provider_iss:
                # Try exact (user, provider, provider_sub) lookup
                existing = await _get_token(uid, "google", provider_sub)
                if existing and getattr(existing, "provider_iss", None):
                    provider_iss = existing.provider_iss
            # Additional guard: if we still lack provider_iss, try any valid google token for uid
            if not provider_iss:
                existing_any = await _get_token(uid, "google")
                if existing_any and getattr(existing_any, "provider_iss", None):
                    provider_iss = existing_any.provider_iss

            if existing := await _get_token(uid, "google"):
                # If an existing valid row has a provider_sub and incoming sub present,
                # ensure they match to avoid accidental account mixing
                if getattr(existing, "provider_sub", None) and provider_sub and str(provider_sub) != str(existing.provider_sub):
                    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                    return RedirectResponse(f"{frontend_url}/settings#google?google_error=account_mismatch", status_code=303)
        except Exception:
            pass

        # If provider_iss is still missing, fail - do not insert rows with NULL provider_iss
        if not provider_iss:
            # In development/test mode, be permissive: apply a Google issuer fallback
            # to allow test mocks that don't include id_token to proceed.
            if dev_mode:
                logger.warning(
                    "Development mode: missing provider_iss, applying fallback issuer",
                    extra={"meta": {"req_id": req_id}},
                )
                provider_iss = "https://accounts.google.com"
            else:
                # Provide specific diagnostic information
                has_id_token = getattr(creds, "id_token", None) is not None
                id_token_length = len(getattr(creds, "id_token", "") or "")

                error_detail = "missing_provider_iss"
                hint_parts = []

                if not has_id_token:
                    error_detail = "google_no_id_token"
                    hint_parts.append(
                        "Google OAuth did not return an id_token - check Cloud Console client configuration"
                    )
                else:
                    hint_parts.append(
                        "Google returned an id_token but it was malformed or missing the 'iss' claim"
                    )

                hint_parts.append("Verify that your Google OAuth client has OpenID Connect enabled")
                hint_parts.append("Ensure 'openid' scope is requested and supported by your client")

                logger.error(
                    "Google OAuth provider_iss validation failed",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "component": "google_oauth",
                            "msg": "provider_iss_validation_failed",
                            "has_id_token": has_id_token,
                            "id_token_length": id_token_length,
                            "has_provider_sub": provider_sub is not None,
                            "scopes_requested": creds.scope,
                            "error_detail": error_detail,
                        }
                    },
                )

                raise_enveloped(
                    "invalid_state",
                    error_detail,
                    hint="; ".join(hint_parts),
                    status=400,
                )

        # Also persist to the shared ThirdPartyToken store so UI status and
        # management endpoints can detect connection state consistently.
        try:
            from ..models.third_party_tokens import ThirdPartyToken
            from ..auth_store_tokens import upsert_token

            now = int(time.time())
            expiry = rec.get("expiry")
            try:
                expires_at = int(expiry.timestamp()) if hasattr(expiry, "timestamp") else int(time.mktime(expiry.timetuple()))  # type: ignore[attr-defined]
            except Exception:
                expires_at = now + int(rec.get("expires_in", 3600))

            # Require identity to be present; fail fast if we can't associate
            if not identity_id_used:
                frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
                return RedirectResponse(f"{frontend_url}/settings#google?google_error=identity_link_failed", status_code=303)

            token = ThirdPartyToken(
                id=f"google:{secrets.token_hex(8)}",
                user_id=uid,
                identity_id=identity_id_used,
                provider="google",
                provider_sub=str(provider_sub) if provider_sub else None,
                provider_iss=str(provider_iss) if provider_iss else None,
                access_token=rec.get("access_token", ""),
                refresh_token=rec.get("refresh_token"),
                scopes=rec.get("scopes"),
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            # Upsert asynchronously (function is async)
            await upsert_token(token)
            logger.info(
                "Third-party token upserted for Google",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "component": "google_oauth",
                        "msg": "third_party_token_upserted",
                        "user_id": uid,
                    }
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to upsert ThirdPartyToken (non-fatal)",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "component": "google_oauth",
                        "msg": "third_party_token_upsert_failed",
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

        # Set tokens as HttpOnly cookies and redirect to frontend
        # Prefer the next URL cookie set during connect/initiation. If it's a
        # relative path (e.g., "/settings"), resolve it against the frontend
        # origin so we don't redirect to the backend (8000) by accident.
        from urllib.parse import urlparse

        # Determine best frontend base
        frontend_base = app_url.rstrip("/")
        try:
            # If APP_URL points at backend host:port, try to use request origin
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
                    frontend_base = f"{op.scheme}://{op.netloc}"
        except Exception:
            pass

        def _resolve_next(n: str) -> str:
            if not n:
                return f"{frontend_base}/"
            # If absolute, return as-is after allowlist
            if n.startswith("http://") or n.startswith("https://"):
                return n
            # Treat as relative path
            if not n.startswith("/"):
                n = "/" + n
            return f"{frontend_base}{n}"

        if next_cookie and _allow_redirect(next_cookie):
            final_root = _resolve_next(next_cookie)
        else:
            final_root = f"{frontend_base}/"

        # Append token query params to the redirect target so frontend can
        # pick up `access_token`/`refresh_token` when present (header-mode flows).
        # Important: if final_root contains a fragment (#), insert query params
        # before the fragment per URL rules so the browser preserves the fragment
        # while the frontend can read the tokens from the query string.
        try:
            if q:
                # Split off fragment if present
                frag = ""
                if "#" in final_root:
                    base_part, frag = final_root.split("#", 1)
                    base_part = base_part.rstrip("/")
                else:
                    base_part = final_root

                if "?" in base_part:
                    new_base = f"{base_part}&{q}"
                else:
                    new_base = f"{base_part}?{q}"

                final_root = f"{new_base}{('#' + frag) if frag else ''}"
        except Exception:
            # Defensive: if q is undefined or any error occurs, fall back silently
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

            # Use 302 (Found) to be compatible with tests and common browser behavior
            resp = RedirectResponse(url=final_root, status_code=302)

        session_id = None
        if os.getenv("ENABLE_SESSION_COOKIE", "") in ("1", "true", "yes"):
            # Create opaque session ID instead of using JWT
            try:
                from ..auth import _create_session_id

                payload = jwt_decode(at, os.getenv("JWT_SECRET"), algorithms=["HS256"])
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
        from ..web.cookies import set_auth_cookies

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
            if cookie_cfg._get_scheme(request) != "https":
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

        # Rotate session and CSRF on login to prevent replay from old anon sessions
        try:
            from ..web.cookies import read_session_cookie, set_csrf_cookie
            from ..auth import _delete_session_id

            session_before = read_session_cookie(request)
        except Exception:
            session_before = None

        # If there is an existing session, delete it (rotate)
        try:
            if session_before:
                try:
                    _delete_session_id(session_before)
                except Exception:
                    # best-effort cleanup
                    pass
        except Exception:
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

        # Rotate CSRF token: set only when using HTML shim (cookies on 200 responses)
        try:
            if use_html_shim:
                import secrets as _secrets

                csrf_token = _secrets.token_urlsafe(16)
                # Short TTL for CSRF token (e.g., 1 hour)
                from ..web.cookies import set_csrf_cookie

                set_csrf_cookie(resp, token=csrf_token, ttl=3600, request=request)
        except Exception:
            pass

        # Telemetry: log canonical handoff details and session rotation info
        try:
            logger.info(
                "oauth.login_telemetry",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "login_user_id": uid,
                        "identity_id": identity_id_used,
                        "provider_sub": provider_sub,
                        "email": email,
                        "session_before": session_before,
                        "session_after": session_id,
                    }
                },
            )
        except Exception:
            pass

        # Emit compact cookie-write observability so ops can verify attributes/names at a glance
        try:
            # Report canonical names in logs
            try:
                from ..web.cookies import NAMES
                cookie_names_written = [NAMES.access, NAMES.refresh]
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

        # Clear OAuth state cookies on the final response
        try:
            from ..cookies import clear_oauth_state_cookies

            clear_oauth_state_cookies(resp, request, provider="g")
        except Exception:
            pass

        # Log auth context
        # Emit GOOGLE_CALLBACK_SUCCESS metric
        try:
            from ..metrics import GOOGLE_CALLBACK_SUCCESS
            import hashlib
            scopes_hash = hashlib.sha256(" ".join(sorted(rec.get("scopes", []))).encode()).hexdigest()[:8]
            GOOGLE_CALLBACK_SUCCESS.labels(user_id=uid, scopes_hash=scopes_hash).inc()
        except Exception:
            pass

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

        # Emit GOOGLE_TOKEN_EXCHANGE_FAILED metric
        try:
            from ..metrics import GOOGLE_TOKEN_EXCHANGE_FAILED
            GOOGLE_TOKEN_EXCHANGE_FAILED.labels(user_id="unknown", reason=str(reason_code)).inc()
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


# Compatibility: some tests call the legacy root-level path `/google/oauth/callback`.
# Delegate to the integration's legacy handler when available.
@router.get("/google/oauth/callback")
async def google_callback_root(request: Request) -> Response:
    try:
        from ..integrations.google.routes import legacy_oauth_callback
    except Exception:
        raise HTTPException(status_code=404)

    maybe = legacy_oauth_callback(request)
    if inspect.isawaitable(maybe):
        return await maybe
    return maybe
