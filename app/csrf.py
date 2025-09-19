from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from secrets import token_urlsafe
from typing import Optional

from fastapi import Request, Depends, HTTPException, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.errors import json_error

logger = logging.getLogger(__name__)


def _truthy(env_val: str | None) -> bool:
    if env_val is None:
        return False
    return str(env_val).strip().lower() in {"1", "true", "yes", "on"}


class CSRFTokenService:
    """Header-token CSRF protection service using HMAC-signed tokens with TTL."""

    def __init__(self):
        self.secret_key = os.getenv("CSRF_SECRET_KEY", os.getenv("JWT_SECRET", "dev-secret-key"))
        self.ttl_seconds = int(os.getenv("CSRF_TTL_SECONDS", "900"))  # 15 minutes default
        self._token_store: dict[str, float] = {}  # Simple in-memory store for demo

    def generate_token(self) -> str:
        """Generate a new CSRF token with timestamp and HMAC signature."""
        # Generate random token
        raw_token = token_urlsafe(16)  # 128-bit token
        timestamp = str(int(time.time()))

        # Create payload: token.timestamp
        payload = f"{raw_token}.{timestamp}"

        # Create HMAC signature
        signature = hmac.new(
            self.secret_key.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

        # Return signed token: token.timestamp.signature
        return f"{payload}.{signature}"

    def validate_token(self, token: str) -> bool:
        """Validate CSRF token signature and TTL."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return False

            raw_token, timestamp_str, signature = parts

            # Check TTL
            timestamp = int(timestamp_str)
            if time.time() - timestamp > self.ttl_seconds:
                logger.warning("csrf.token_expired")
                return False

            # Recreate payload and verify signature
            payload = f"{raw_token}.{timestamp_str}"
            expected_signature = hmac.new(
                self.secret_key.encode(),
                payload.encode(),
                hashlib.sha256
            ).hexdigest()

            if not hmac.compare_digest(signature, expected_signature):
                logger.warning("csrf.token_invalid_signature")
                return False

            return True

        except (ValueError, IndexError) as e:
            logger.warning(f"csrf.token_malformed: {e}")
            return False

    def store_token(self, token: str) -> None:
        """Store token for additional validation if needed."""
        # For now, just track creation time
        self._token_store[token] = time.time()

    def cleanup_expired_tokens(self) -> None:
        """Clean up expired tokens from store."""
        current_time = time.time()
        expired = [
            token for token, created_time in self._token_store.items()
            if current_time - created_time > self.ttl_seconds
        ]
        for token in expired:
            del self._token_store[token]


# Global CSRF token service instance
_csrf_service = CSRFTokenService()


def get_csrf_token() -> str:
    """Generate a new CSRF token."""
    token = _csrf_service.generate_token()
    _csrf_service.store_token(token)
    return token


def issue_csrf_token(response: Response, request: Request | None = None) -> str:
    """Mint a CSRF token, attach header + cookie, and persist for validation."""

    token = get_csrf_token()
    ttl = getattr(_csrf_service, "ttl_seconds", int(os.getenv("CSRF_TTL_SECONDS", "900")))

    try:
        response.headers["X-CSRF-Token"] = token
    except Exception as exc:  # pragma: no cover - header assignment failure
        logger.debug("csrf.header_set_failed: %s", exc)

    try:
        _csrf_token_store.store_token(token, ttl)
    except Exception as exc:  # pragma: no cover - best effort store
        logger.debug("csrf.store_failed: %s", exc)

    try:
        from app.web.cookies import set_csrf_cookie

        set_csrf_cookie(response, token=token, ttl=ttl, request=request)
    except Exception as exc:  # pragma: no cover - cookie best effort
        logger.debug("csrf.cookie_set_failed: %s", exc)

    return token


def require_csrf(request: Request) -> None:
    """Dependency to validate CSRF token from X-CSRF-Token header."""
    if not _truthy(os.getenv("CSRF_ENABLED", "0")):
        return  # CSRF disabled

    # Skip for safe methods
    if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return

    # Skip for Bearer-only auth
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        session_cookie = (
            request.cookies.get("GSNH_AT") or
            request.cookies.get("GSNH_SESS") or
            request.cookies.get("access_token") or
            request.cookies.get("session")
        )
        if not session_cookie:
            return  # Bearer-only auth, skip CSRF

    # Skip OAuth callbacks
    path = getattr(getattr(request, "url", None), "path", "") or ""
    oauth_callbacks = {
        "/v1/auth/apple/callback",
        "/auth/apple/callback",
        "/v1/auth/google/callback",
    }
    if path in oauth_callbacks:
        return

    # Skip webhook endpoints with signature
    webhook_paths = {"/v1/ha/webhook", "/ha/webhook"}
    if path in webhook_paths:
        signature = request.headers.get("X-Signature") or request.headers.get("X-Hub-Signature")
        if signature:
            return

    # Require CSRF token
    csrf_token = request.headers.get("X-CSRF-Token")
    if not csrf_token:
        logger.warning("csrf.missing_header")
        raise HTTPException(status_code=403, detail="CSRF token required")

    if not _csrf_service.validate_token(csrf_token):
        logger.warning("csrf.token_invalid")
        raise HTTPException(status_code=403, detail="Invalid CSRF token")


def _extract_csrf_header(request: Request) -> tuple[str | None, bool, bool]:
    """Return (token, used_legacy, legacy_allowed).

    - Prefer X-CSRF-Token
    - Accept legacy X-CSRF only when CSRF_LEGACY_GRACE is truthy
    - Emit a warning via print when legacy is used and allowed
    """
    token = request.headers.get("X-CSRF-Token")
    if token:
        return token, False, False
    legacy = request.headers.get("X-CSRF")
    if legacy:
        allowed = _truthy(os.getenv("CSRF_LEGACY_GRACE", "1"))
        if allowed:
            try:
                # Log with explicit deprecation date for ops visibility
                logger.warning("csrf.legacy_header used removal=2025-12-31")
            except Exception:
                pass
        return legacy, True, allowed
    return None, False, False


class CSRFMiddleware(BaseHTTPMiddleware):
    """Header-token CSRF protection service.

    - Allow safe methods (GET/HEAD/OPTIONS).
    - Skip for Bearer-only auth (Authorization header present, no session cookie).
    - Skip for webhooks with signature verification.
    - Skip OAuth callbacks with state/nonce validation.
    - For POST/PUT/PATCH/DELETE, require valid X-CSRF-Token header.
    - Uses HMAC-signed tokens with TTL instead of double-submit cookies.
    - Disabled when CSRF_ENABLED=0.
    """

    async def dispatch(self, request: Request, call_next):
        # Default disabled globally; enable per app/env via CSRF_ENABLED=1
        if not _truthy(os.getenv("CSRF_ENABLED", "0")):
            return await call_next(request)

        # For safe methods, provide CSRF token in response header
        if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
            try:
                response = await call_next(request)
            except Exception:
                # Even on exceptions, we need to ensure CSRF headers are set
                response = json_error(
                    code="internal_error",
                    message="Something went wrong",
                    http_status=500,
                )

            # Generate and provide CSRF token for client
            try:
                csrf_token = get_csrf_token()
                response.headers["X-CSRF-Token"] = csrf_token
            except Exception as e:
                logger.debug(f"csrf.token_generation_failed: {e}")

            return response

        # Skip CSRF validation for Bearer-only auth
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # Check if there are any session cookies
            session_cookie = (
                request.cookies.get("GSNH_AT") or
                request.cookies.get("GSNH_SESS") or
                request.cookies.get("access_token") or
                request.cookies.get("session")
            )
            if not session_cookie:
                logger.info("bypass: csrf_bearer_only_auth")
                return await call_next(request)

        # Skip OAuth callbacks
        try:
            path = getattr(getattr(request, "url", None), "path", "") or ""
            oauth_callbacks = {
                "/v1/auth/apple/callback",
                "/auth/apple/callback",
                "/v1/auth/google/callback",
            }
            if path in oauth_callbacks:
                logger.info("bypass: csrf_oauth_callback path=<%s>", path)
                return await call_next(request)
        except Exception:
            pass

        # Skip webhook endpoints with signature verification
        try:
            path = getattr(getattr(request, "url", None), "path", "") or ""
            webhook_paths = {"/v1/ha/webhook", "/ha/webhook"}
            if path in webhook_paths:
                signature = request.headers.get("X-Signature") or request.headers.get("X-Hub-Signature")
                if signature:
                    logger.info("bypass: csrf_webhook_signature path=<%s>", path)
                    return await call_next(request)
        except Exception:
            pass

        # Check for route-level CSRF opt-out
        try:
            csrf_opt_out = request.headers.get("X-CSRF-Opt-Out") or request.query_params.get("csrf_opt_out")
            if csrf_opt_out and _truthy(csrf_opt_out):
                logger.info("bypass: csrf_route_opt_out")
                return await call_next(request)
        except Exception:
            pass

        # Check if this is a public route (no CSRF required)
        try:
            # Access the endpoint function to check for public_route decorator
            endpoint = getattr(request, 'scope', {}).get('endpoint')
            if endpoint and hasattr(endpoint, '__doc__') and endpoint.__doc__:
                docstring = endpoint.__doc__
                if "@public_route - No auth, no CSRF required" in docstring:
                    logger.info("bypass: csrf_public_route")
                    return await call_next(request)
        except Exception as e:
            logger.debug(f"csrf.endpoint_check_failed: {e}")

        # Require valid CSRF token in header
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            logger.warning("csrf.missing_header")
            return json_error(
                code="csrf.missing", message="CSRF token required", http_status=403
            )

        if not _csrf_service.validate_token(csrf_token):
            logger.warning("csrf.token_invalid")
            return json_error(
                code="csrf.invalid", message="Invalid CSRF token", http_status=403
            )

        logger.info("csrf.token_valid")
        return await call_next(request)


def get_csrf_token() -> str:
    """Generate a new CSRF token for header-based CSRF protection.

    Returns a cryptographically strong token with HMAC signature and TTL.
    Used by the /v1/csrf endpoint and middleware.
    """
    token = _csrf_service.generate_token()
    _csrf_service.store_token(token)
    return token


class CSRFTokenStore:
    """Server-side storage for CSRF tokens to enhance cross-site security.

    Stores valid CSRF tokens with TTL for validation in cross-site scenarios.
    Falls back to in-memory storage if Redis is not available.
    """

    def __init__(self):
        self._local_store = {}
        self._redis_available = self._check_redis_available()

    def _check_redis_available(self) -> bool:
        """Check if Redis is available for token storage."""
        try:
            redis_url = os.getenv("REDIS_URL")
            if not redis_url:
                return False
            import redis

            client = redis.from_url(redis_url)
            client.ping()
            return True
        except Exception:
            return False

    def _get_redis_client(self):
        """Get Redis client if available."""
        if not self._redis_available:
            return None
        try:
            import redis

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            return redis.from_url(redis_url)
        except Exception:
            return None

    def store_token(self, token: str, ttl_seconds: int = 600) -> None:
        """Store a CSRF token with TTL for server-side validation."""
        if self._redis_available:
            try:
                client = self._get_redis_client()
                if client:
                    key = f"csrf_token:{token}"
                    client.setex(key, ttl_seconds, "valid")
                    logger.debug(
                        "csrf_token_stored_redis token=<%s> ttl=%d",
                        token[:8] + "...",
                        ttl_seconds,
                    )
                    return
            except Exception as e:
                logger.warning("csrf_token_store_redis_failed error=%s", str(e))

        # Fallback to in-memory storage
        expires_at = time.time() + ttl_seconds
        self._local_store[token] = expires_at
        logger.debug(
            "csrf_token_stored_memory token=<%s> ttl=%d", token[:8] + "...", ttl_seconds
        )

        # Clean up expired tokens periodically
        self._cleanup_expired()

    def validate_token(self, token: str) -> bool:
        """Validate a CSRF token against server-side storage."""
        if self._redis_available:
            try:
                client = self._get_redis_client()
                if client:
                    key = f"csrf_token:{token}"
                    result = client.get(key)
                    if result:
                        logger.debug(
                            "csrf_token_validated_redis token=<%s>", token[:8] + "..."
                        )
                        return True
            except Exception as e:
                logger.warning("csrf_token_validate_redis_failed error=%s", str(e))

        # Check in-memory storage
        if token in self._local_store:
            expires_at = self._local_store[token]
            if time.time() < expires_at:
                logger.debug(
                    "csrf_token_validated_memory token=<%s>", token[:8] + "..."
                )
                return True
            else:
                # Token expired, remove it
                del self._local_store[token]

        return False

    def _cleanup_expired(self) -> None:
        """Clean up expired tokens from in-memory storage."""
        current_time = time.time()
        expired_tokens = [
            token
            for token, expires_at in self._local_store.items()
            if current_time >= expires_at
        ]
        for token in expired_tokens:
            del self._local_store[token]
        if expired_tokens:
            logger.debug("csrf_token_cleanup_removed count=%d", len(expired_tokens))


# Global CSRF token store instance
_csrf_token_store = CSRFTokenStore()


__all__ = ["CSRFMiddleware", "get_csrf_token", "issue_csrf_token", "_extract_csrf_header"]
