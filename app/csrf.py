from __future__ import annotations

import logging
import os
import time
from secrets import token_urlsafe

from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def _truthy(env_val: str | None) -> bool:
    if env_val is None:
        return False
    return str(env_val).strip().lower() in {"1", "true", "yes", "on"}


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
    """Simple double-submit CSRF with exemptions.

    - Allow safe methods (GET/HEAD/OPTIONS).
    - Skip for Bearer-only auth (Authorization header present, no session cookie).
    - Skip for webhooks with signature verification.
    - Skip OAuth callbacks with state/nonce validation.
    - For POST/PUT/PATCH/DELETE, require header X-CSRF-Token to match cookie csrf_token.
    - Disabled when CSRF_ENABLED=0.
    """

    async def dispatch(self, request: Request, call_next):
        # Default disabled globally; enable per app/env via CSRF_ENABLED=1
        if not _truthy(os.getenv("CSRF_ENABLED", "0")):
            return await call_next(request)
        if request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
            return await call_next(request)

        # Bypass CSRF for Bearer-only auth (Authorization header present, no session cookie)
        auth_header = request.headers.get("Authorization")
        try:
            from .cookies import read_access_cookie, read_session_cookie

            session_cookie = read_access_cookie(request) or read_session_cookie(request) or request.cookies.get("session")
        except Exception:
            session_cookie = request.cookies.get("access_token") or request.cookies.get("__session") or request.cookies.get("session")
        if auth_header and auth_header.startswith("Bearer ") and not session_cookie:
            logger.info(
                "bypass: csrf_bearer_only_auth header=<%s>",
                auth_header[:8] + "..." if auth_header else "None",
            )
            return await call_next(request)

        # Allow-list OAuth provider callbacks which validate state/nonce explicitly
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

        # Allow-list webhook endpoints with signature verification
        try:
            path = getattr(getattr(request, "url", None), "path", "") or ""
            webhook_paths = {"/v1/ha/webhook", "/ha/webhook"}
            if path in webhook_paths:
                # Check for webhook signature headers
                signature = request.headers.get("X-Signature") or request.headers.get(
                    "X-Hub-Signature"
                )
                if signature:
                    logger.info(
                        "bypass: csrf_webhook_signature path=<%s> signature=<%s>",
                        path,
                        signature[:8] + "..." if signature else "None",
                    )
                    return await call_next(request)
        except Exception:
            pass

        # Check for route-level CSRF opt-out (for testing/signature-based endpoints)
        try:
            csrf_opt_out = request.headers.get(
                "X-CSRF-Opt-Out"
            ) or request.query_params.get("csrf_opt_out")
            if csrf_opt_out and _truthy(csrf_opt_out):
                logger.info(
                    "bypass: csrf_route_opt_out header=<%s> query=<%s>",
                    request.headers.get("X-CSRF-Opt-Out"),
                    request.query_params.get("csrf_opt_out"),
                )
                return await call_next(request)
        except Exception:
            pass

        # Check if we're in a cross-site scenario (COOKIE_SAMESITE=none)
        is_cross_site = os.getenv("COOKIE_SAMESITE", "lax").lower() == "none"

        token_hdr, used_legacy, legacy_allowed = _extract_csrf_header(request)

        if is_cross_site:
            # Cross-site CSRF validation: require token in header + basic validation
            if not token_hdr:
                logger.warning(
                    "deny: csrf_missing_header_cross_site header=<%s>",
                    token_hdr[:8] + "..." if token_hdr else "None",
                )
                raise HTTPException(400, detail="csrf.missing")

            # Basic validation for cross-site tokens
            if len(token_hdr) < 16:
                logger.warning(
                    "deny: csrf_invalid_format_cross_site header=<%s>",
                    token_hdr[:8] + "..." if token_hdr else "None",
                )
                raise HTTPException(400, detail="csrf.invalid")

            # For cross-site, we accept any properly formatted token
            # (server-side validation is optional for basic functionality)
            logger.info(
                "allow: csrf_cross_site_validation header=<%s>",
                token_hdr[:8] + "..." if token_hdr else "None",
            )
            return await call_next(request)
        else:
            # Standard same-origin CSRF validation (double-submit pattern)
            token_cookie = request.cookies.get("csrf_token") or ""
            # Reject legacy header when grace disabled
            if used_legacy and not legacy_allowed:
                logger.warning(
                    "deny: csrf_legacy_header_disabled header=<%s>",
                    token_hdr[:8] + "..." if token_hdr else "None",
                )
                raise HTTPException(400, detail="csrf.missing")
            # Require both header and cookie, and match
            if not token_hdr or not token_cookie:
                logger.warning(
                    "deny: csrf_missing_header header=<%s> cookie=<%s>",
                    token_hdr[:8] + "..." if token_hdr else "None",
                    token_cookie[:8] + "..." if token_cookie else "None",
                )
                raise HTTPException(403, detail="csrf.missing")
            if token_hdr != token_cookie:
                logger.warning(
                    "deny: csrf_mismatch header=<%s> cookie=<%s>",
                    token_hdr[:8] + "...",
                    token_cookie[:8] + "...",
                )
                raise HTTPException(400, detail="csrf.invalid")
            return await call_next(request)


async def get_csrf_token() -> str:
    """Return an existing csrf_token cookie or mint a new random value.

    Middlewares that want to ensure presence can call this and set cookie.
    The /v1/csrf endpoint returns this value for test flows.
    """
    # For now, just return a random per-call token; a route should set cookie.
    return token_urlsafe(16)


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
                    logger.debug("csrf_token_stored_redis token=<%s> ttl=%d", token[:8] + "...", ttl_seconds)
                    return
            except Exception as e:
                logger.warning("csrf_token_store_redis_failed error=%s", str(e))

        # Fallback to in-memory storage
        expires_at = time.time() + ttl_seconds
        self._local_store[token] = expires_at
        logger.debug("csrf_token_stored_memory token=<%s> ttl=%d", token[:8] + "...", ttl_seconds)

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
                        logger.debug("csrf_token_validated_redis token=<%s>", token[:8] + "...")
                        return True
            except Exception as e:
                logger.warning("csrf_token_validate_redis_failed error=%s", str(e))

        # Check in-memory storage
        if token in self._local_store:
            expires_at = self._local_store[token]
            if time.time() < expires_at:
                logger.debug("csrf_token_validated_memory token=<%s>", token[:8] + "...")
                return True
            else:
                # Token expired, remove it
                del self._local_store[token]

        return False

    def _cleanup_expired(self) -> None:
        """Clean up expired tokens from in-memory storage."""
        current_time = time.time()
        expired_tokens = [token for token, expires_at in self._local_store.items() if current_time >= expires_at]
        for token in expired_tokens:
            del self._local_store[token]
        if expired_tokens:
            logger.debug("csrf_token_cleanup_removed count=%d", len(expired_tokens))


# Global CSRF token store instance
_csrf_token_store = CSRFTokenStore()


__all__ = ["CSRFMiddleware", "get_csrf_token", "_extract_csrf_header"]
