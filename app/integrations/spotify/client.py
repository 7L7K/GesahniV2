from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx

from ...auth_store_tokens import get_token, mark_invalid, upsert_token
from ...http_utils import json_request
from ...metrics import SPOTIFY_429, SPOTIFY_LATENCY, SPOTIFY_REFRESH, SPOTIFY_REQUESTS
from ...models.third_party_tokens import ThirdPartyToken
from .budget import get_spotify_budget_manager
from .oauth import SpotifyOAuth, SpotifyOAuthError

logger = logging.getLogger(__name__)

# Enhanced logging configuration
logging.basicConfig(level=logging.DEBUG)
logger.setLevel(logging.DEBUG)


def log_spotify_operation(
    operation: str, user_id: str, details: dict = None, level: str = "info"
):
    """Enhanced Spotify operation logging."""
    details = details or {}
    log_data = {
        "operation": operation,
        "user_id": user_id,
        "timestamp": time.time(),
        **details,
    }

    if level == "debug":
        logger.debug(f"🎵 SPOTIFY {operation.upper()}", extra={"meta": log_data})
    elif level == "warning":
        logger.warning(f"🎵 SPOTIFY {operation.upper()}", extra={"meta": log_data})
    elif level == "error":
        logger.error(f"🎵 SPOTIFY {operation.upper()}", extra={"meta": log_data})
    else:
        logger.info(f"🎵 SPOTIFY {operation.upper()}", extra={"meta": log_data})


@dataclass
class SpotifyTokens:
    """Spotify token data structure."""

    access_token: str
    refresh_token: str
    expires_at: float
    scope: str | None = None


class SpotifyAuthError(RuntimeError):
    """Exception raised for Spotify authentication errors."""

    pass


class SpotifyPremiumRequiredError(SpotifyAuthError):
    """Raised when the account lacks Premium required for playback."""


class SpotifyRateLimitedError(SpotifyAuthError):
    """Raised when Spotify responds with 429 and includes Retry-After."""

    def __init__(self, retry_after: int | None = None, *args: object) -> None:
        super().__init__(*args)
        self.retry_after = retry_after


class SpotifyClient:
    """Spotify Web API client with unified token storage and budget support."""

    api_base = "https://api.spotify.com/v1"

    def __init__(self, user_id: str) -> None:
        log_spotify_operation(
            "client_init",
            user_id,
            {"message": "Initializing SpotifyClient", "user_id": user_id},
        )

        self.user_id = user_id
        self.oauth = SpotifyOAuth()
        self._circuit_breaker_state = {"failures": 0, "last_failure": 0.0}
        self._budget_manager = get_spotify_budget_manager(user_id)

        log_spotify_operation(
            "client_init_complete",
            user_id,
            {
                "message": "SpotifyClient initialized successfully",
                "budget_manager_created": True,
                "oauth_client_created": True,
            },
        )

    # ------------------------------------------------------------------
    # Token management with unified storage
    # ------------------------------------------------------------------

    async def _get_tokens(self) -> SpotifyTokens | None:
        """Retrieve tokens from unified token store."""
        log_spotify_operation(
            "token_retrieval_start",
            self.user_id,
            {"message": "Starting token retrieval from store", "method": "_get_tokens"},
        )

        try:
            token = await get_token(self.user_id, "spotify")

            log_spotify_operation(
                "token_retrieval_result",
                self.user_id,
                {
                    "message": "Token retrieval completed",
                    "has_token": token is not None,
                    "token_id": getattr(token, "id", None) if token else None,
                    "token_user_id": getattr(token, "user_id", None) if token else None,
                    "token_provider": (
                        getattr(token, "provider", None) if token else None
                    ),
                    "has_access_token": (
                        bool(getattr(token, "access_token", None)) if token else False
                    ),
                    "has_refresh_token": (
                        bool(getattr(token, "refresh_token", None)) if token else False
                    ),
                    "expires_at": getattr(token, "expires_at", None) if token else None,
                    "scope": getattr(token, "scope", None) if token else None,
                    "current_time": time.time(),
                },
            )

            if not token:
                log_spotify_operation(
                    "token_not_found",
                    self.user_id,
                    {"message": "No Spotify token found in store", "level": "warning"},
                    level="warning",
                )
                return None

            # Validate token data
            if not getattr(token, "access_token", None):
                log_spotify_operation(
                    "token_missing_access",
                    self.user_id,
                    {
                        "message": "Token found but missing access_token",
                        "level": "error",
                    },
                    level="error",
                )
                return None

            spotify_tokens = SpotifyTokens(
                access_token=token.access_token,
                refresh_token=getattr(token, "refresh_token", None),
                expires_at=getattr(token, "expires_at", 0),
                scope=getattr(token, "scope", None),
            )

            log_spotify_operation(
                "token_validation_success",
                self.user_id,
                {
                    "message": "Token validation successful",
                    "has_refresh_token": bool(spotify_tokens.refresh_token),
                    "expires_in_seconds": max(
                        0, spotify_tokens.expires_at - time.time()
                    ),
                },
            )

            return spotify_tokens

        except Exception as e:
            log_spotify_operation(
                "token_retrieval_error",
                self.user_id,
                {
                    "message": "Error retrieving Spotify tokens",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "level": "error",
                },
                level="error",
            )
            raise

    async def _store_tokens(self, tokens: SpotifyTokens) -> None:
        """Store tokens in unified token store."""
        # Preserve identity_id/provider_sub/provider_iss from existing stored token
        identity_id = None
        provider_sub = None
        provider_iss = None
        try:
            cur = await get_token(self.user_id, "spotify")
            if cur:
                identity_id = getattr(cur, "identity_id", None)
                provider_sub = getattr(cur, "provider_sub", None)
                provider_iss = getattr(cur, "provider_iss", None)
        except Exception as e:
            logger.warning(
                "Failed to get existing token metadata",
                extra={"meta": {"user_id": self.user_id, "error": str(e)}},
            )

        token = ThirdPartyToken(
            user_id=self.user_id,
            provider="spotify",
            identity_id=identity_id,
            provider_sub=provider_sub,
            provider_iss=provider_iss,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            scopes=tokens.scope,
            expires_at=tokens.expires_at,
            created_at=int(time.time()),
            updated_at=int(time.time()),
            is_valid=True,
        )
        await upsert_token(token)

    async def _refresh_tokens(self) -> SpotifyTokens:
        """Refresh access token using refresh token."""
        current_tokens = await self._get_tokens()
        if not current_tokens or not current_tokens.refresh_token:
            raise SpotifyAuthError("No refresh token available")

        try:
            token_data = await self.oauth.refresh_access_token(
                current_tokens.refresh_token
            )

            new_tokens = SpotifyTokens(
                access_token=token_data["access_token"],
                refresh_token=token_data.get(
                    "refresh_token", current_tokens.refresh_token
                ),
                expires_at=int(token_data["expires_at"]),
                scope=token_data.get("scope", current_tokens.scope),
            )

            await self._store_tokens(new_tokens)
            return new_tokens

        except SpotifyOAuthError as e:
            raise SpotifyAuthError(f"Token refresh failed: {e}")

    async def _refresh_access_token(self) -> dict[str, Any]:
        """Compat: refresh and return a dict with new access and expiry.

        Tests patch this method; production code prefers _refresh_tokens().
        """
        new_tokens = await self._refresh_tokens()
        return {"access_token": new_tokens.access_token, "expires_at": new_tokens.expires_at}

    async def disconnect(self) -> bool:
        """Disconnect by marking tokens as invalid."""
        # Prefer instance-based DAO so tests patching TokenDAO see the change
        try:
            from ...auth_store_tokens import TokenDAO as _TokenDAO

            dao = _TokenDAO()
            ok = await dao.mark_invalid(self.user_id, "spotify")
            if ok:
                return True
        except Exception:
            pass
        # Fallback to global convenience
        try:
            return await mark_invalid(self.user_id, "spotify")
        except Exception:
            return False

    async def _get_valid_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        log_spotify_operation(
            "get_valid_access_token_start",
            self.user_id,
            {
                "message": "Starting access token validation",
                "method": "_get_valid_access_token",
            },
        )

        try:
            # Use the new robust token service
            try:
                from app.auth_store_tokens import get_valid_token_with_auto_refresh
            except ImportError:
                # Fallback for relative import issues
                import os
                import sys

                sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
                from app.auth_store_tokens import get_valid_token_with_auto_refresh

            log_spotify_operation(
                "calling_auto_refresh_service",
                self.user_id,
                {
                    "message": "Calling get_valid_token_with_auto_refresh",
                    "force_refresh": False,
                },
            )

            token = await get_valid_token_with_auto_refresh(
                self.user_id, "spotify", force_refresh=False
            )

            log_spotify_operation(
                "auto_refresh_result",
                self.user_id,
                {
                    "message": "Auto-refresh service result",
                    "has_token": token is not None,
                    "token_type": type(token).__name__ if token else None,
                    "token_id": getattr(token, "id", None) if token else None,
                    "has_access_token": (
                        bool(getattr(token, "access_token", None)) if token else False
                    ),
                    "has_refresh_token": (
                        bool(getattr(token, "refresh_token", None)) if token else False
                    ),
                    "expires_at": getattr(token, "expires_at", None) if token else None,
                    "scope": getattr(token, "scope", None) if token else None,
                },
            )

            if not token:
                log_spotify_operation(
                    "no_valid_tokens",
                    self.user_id,
                    {"message": "No valid Spotify tokens found", "level": "error"},
                    level="error",
                )
                raise SpotifyAuthError("No valid Spotify tokens found")

            # Double-check token is not expired (additional safety)
            current_time = int(time.time())
            is_expired_60s = getattr(token, "is_expired", lambda x: True)(60)

            log_spotify_operation(
                "token_expiry_check",
                self.user_id,
                {
                    "message": "Checking token expiry",
                    "expires_at": getattr(token, "expires_at", None),
                    "current_time": current_time,
                    "is_expired_60s": is_expired_60s,
                    "seconds_until_expiry": max(
                        0, getattr(token, "expires_at", 0) - current_time
                    ),
                },
            )

            if is_expired_60s:  # 1 minute buffer
                log_spotify_operation(
                    "token_expired_force_refresh",
                    self.user_id,
                    {
                        "message": "Token expired, forcing refresh",
                        "expires_at": getattr(token, "expires_at", None),
                        "level": "warning",
                    },
                    level="warning",
                )

                # Force refresh if still expired
                token = await get_valid_token_with_auto_refresh(
                    self.user_id, "spotify", force_refresh=True
                )

                log_spotify_operation(
                    "force_refresh_result",
                    self.user_id,
                    {
                        "message": "Force refresh result",
                        "has_token_after_refresh": token is not None,
                    },
                )

                if not token:
                    log_spotify_operation(
                        "refresh_failed",
                        self.user_id,
                        {
                            "message": "Failed to refresh Spotify token",
                            "level": "error",
                        },
                        level="error",
                    )
                    raise SpotifyAuthError("Failed to refresh Spotify token")

            # Final validation
            access_token = getattr(token, "access_token", "")
            if not access_token:
                log_spotify_operation(
                    "no_access_token_after_refresh",
                    self.user_id,
                    {"message": "No access token after refresh", "level": "error"},
                    level="error",
                )
                raise SpotifyAuthError("No access token available")

            log_spotify_operation(
                "valid_access_token_returned",
                self.user_id,
                {
                    "message": "Returning valid access token",
                    "token_length": len(access_token),
                    "expires_at": getattr(token, "expires_at", None),
                    "seconds_until_expiry": max(
                        0, getattr(token, "expires_at", 0) - current_time
                    ),
                },
            )

            return access_token

        except SpotifyAuthError:
            raise
        except Exception as e:
            log_spotify_operation(
                "access_token_error",
                self.user_id,
                {
                    "message": "Unexpected error getting valid access token",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "level": "error",
                },
                level="error",
            )
            raise SpotifyAuthError(f"Failed to get valid access token: {e}")

    # ------------------------------------------------------------------
    # Budget and timeout support
    # ------------------------------------------------------------------

    def _check_budget(self) -> None:
        """Check if user is within budget limits."""
        if self._budget_manager.is_budget_exceeded():
            raise SpotifyAuthError("Budget limit exceeded for Spotify operations")

    def _get_timeout(self) -> float:
        """Get appropriate timeout based on budget and router settings."""
        return self._budget_manager.get_timeout()

    # ------------------------------------------------------------------
    # HTTP client with retry and circuit breaker
    # ------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        retry_on_401: bool = True,
    ) -> httpx.Response:
        """Make authenticated request to Spotify API with retry logic."""
        # Check budget before making request
        self._check_budget()

        # Get timeout for this request
        timeout = self._get_timeout()

        # Build full URL
        url = f"{self.api_base}{path}"

        # Circuit breaker check
        if self._is_circuit_open():
            raise SpotifyAuthError("Circuit breaker open - too many recent failures")

        # Get valid access token
        access_token = await self._get_valid_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        # Make request with retry logic and exponential backoff
        attempt = 0
        max_attempts = 3
        base_delay = 1.0

        while attempt < max_attempts:
            attempt += 1

            try:
                # Use the generic json_request utility with our timeout
                data, error = await json_request(
                    method=method.upper(),
                    url=url,
                    headers=headers,
                    params=params,
                    json=json_body,
                    timeout=timeout,
                )

                if error:
                    if error == "auth_error" and retry_on_401:
                        # Try to refresh token and retry once
                        try:
                            await self._refresh_tokens()
                            access_token = await self._get_valid_access_token()
                            headers["Authorization"] = f"Bearer {access_token}"
                            continue
                        except SpotifyAuthError:
                            raise SpotifyAuthError(
                                "Authentication failed after token refresh"
                            )

                    # Handle other errors
                    self._record_failure()
                    raise SpotifyAuthError(f"Spotify API error: {error}")

                # Success - create a mock response object for compatibility
                class MockResponse:
                    status_code = 200
                    headers: dict[str, Any]

                    def __init__(self, data: Any):
                        self.data = data
                        self.headers = {}

                    def json(self) -> Any:
                        return self.data

                self._record_success()
                return MockResponse(data)  # type: ignore

            except Exception as e:
                self._record_failure()

                if attempt < max_attempts:
                    # Exponential backoff with jitter
                    delay = base_delay * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)
                    continue

                raise SpotifyAuthError(
                    f"Request failed after {max_attempts} attempts: {e}"
                )

        # This should never be reached, but just in case
        raise SpotifyAuthError("Request failed")

    # ------------------------------------------------------------------
    # Lower-level proxy request that preserves HTTP semantics for UI mapping
    # ------------------------------------------------------------------
    async def _proxy_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> httpx.Response:
        """Perform a raw request to Spotify and surface HTTP status codes.

        Retries on 5xx with backoff, refreshes on 401 once, and raises
        specialized exceptions for 403 (premium_required) and 429 (rate_limited).
        """
        logger.info(
            "🎵 SPOTIFY CLIENT: _proxy_request starting",
            extra={
                "meta": {
                    "user_id": self.user_id,
                    "method": method,
                    "path": path,
                    "params": params,
                    "has_json_body": json_body is not None,
                    "json_body_size": len(str(json_body)) if json_body else 0,
                }
            },
        )

        self._check_budget()
        timeout = self._get_timeout()
        url = f"{self.api_base}{path}"

        logger.debug(
            "🎵 SPOTIFY CLIENT: _proxy_request URL constructed",
            extra={
                "meta": {
                    "user_id": self.user_id,
                    "method": method,
                    "url": url,
                    "timeout": timeout,
                }
            },
        )

        # Circuit breaker check
        if self._is_circuit_open():
            raise SpotifyAuthError("Circuit breaker open - too many recent failures")

        # Check if we're in backoff period
        await self._budget_manager.wait_for_backoff()

        access_token = await self._get_valid_access_token()

        headers = {"Authorization": f"Bearer {access_token}"}

        attempt = 0
        while attempt < 3:
            attempt += 1
            logger.debug(
                "🎵 SPOTIFY CLIENT: Making HTTP request",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "attempt": attempt,
                        "method": method,
                        "url": url,
                        "has_params": params is not None,
                        "has_json_body": json_body is not None,
                        "timeout": timeout,
                    }
                },
            )

            async with httpx.AsyncClient(timeout=timeout) as client:
                t0 = perf_counter()
                r = await client.request(
                    method, url, params=params, json=json_body, headers=headers
                )
                dt = perf_counter() - t0

            logger.info(
                "🎵 SPOTIFY CLIENT: HTTP response received",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "attempt": attempt,
                        "method": method,
                        "path": path,
                        "status_code": r.status_code,
                        "response_time_ms": round(dt * 1000, 2),
                        "headers": dict(r.headers),
                        "response_size": len(r.text) if r.text else 0,
                    }
                },
            )

            # observe metrics
            try:
                SPOTIFY_LATENCY.labels(method, path).observe(dt)
                SPOTIFY_REQUESTS.labels(method, path, str(r.status_code)).inc()
            except Exception as e:
                logger.debug(
                    "Failed to record Spotify metrics",
                    extra={"meta": {"error": str(e), "method": method, "path": path}},
                )

            # Handle rate limit explicitly with proper backoff
            if r.status_code == 429:
                logger.warning(
                    "🎵 SPOTIFY CLIENT: Rate limited by Spotify",
                    extra={
                        "meta": {
                            "user_id": self.user_id,
                            "attempt": attempt,
                            "method": method,
                            "path": path,
                            "retry_after_header": (r.headers or {}).get("Retry-After"),
                        }
                    },
                )

                try:
                    SPOTIFY_429.labels(path).inc()
                except Exception as e:
                    logger.debug(
                        "Failed to record Spotify 429 metric",
                        extra={"meta": {"error": str(e), "path": path}},
                    )
                retry_after = None
                try:
                    retry_after = int((r.headers or {}).get("Retry-After", "0") or 0)
                    logger.info(
                        "🎵 SPOTIFY CLIENT: Applying Retry-After backoff",
                        extra={
                            "meta": {
                                "user_id": self.user_id,
                                "retry_after": retry_after,
                            }
                        },
                    )
                    # Apply backoff using the Retry-After header value
                    self._budget_manager.apply_backoff(retry_after)
                except Exception as e:
                    logger.debug(
                        "Failed to apply Retry-After backoff",
                        extra={"meta": {"error": str(e), "retry_after": retry_after}},
                    )
                    # Apply exponential backoff if no Retry-After header
                    logger.info(
                        "🎵 SPOTIFY CLIENT: Applying exponential backoff",
                        extra={"meta": {"user_id": self.user_id}},
                    )
                    self._budget_manager.apply_backoff()
                # Surface a specialized exception for UI
                raise SpotifyRateLimitedError(retry_after, "rate_limited")

            if r.status_code == 401:
                logger.warning(
                    "🎵 SPOTIFY CLIENT: 401 Unauthorized from Spotify",
                    extra={
                        "meta": {
                            "user_id": self.user_id,
                            "attempt": attempt,
                            "method": method,
                            "path": path,
                            "max_attempts": 3,
                        }
                    },
                )

                try:
                    SPOTIFY_REFRESH.inc()
                except Exception as e:
                    logger.debug(
                        "Failed to record Spotify refresh metric",
                        extra={"meta": {"error": str(e)}},
                    )

                # Only attempt refresh on first attempt to avoid infinite loops
                if attempt == 1:
                    logger.info(
                        "🎵 SPOTIFY CLIENT: Attempting token refresh on 401",
                        extra={"meta": {"user_id": self.user_id, "attempt": attempt}},
                    )

                    # Check if token needs refresh based on expiry
                    from app.auth_store_tokens import get_token as _get_token

                    t = await _get_token(self.user_id, "spotify")
                    now = int(time.time())

                    logger.debug(
                        "🎵 SPOTIFY CLIENT: Token status check",
                        extra={
                            "meta": {
                                "user_id": self.user_id,
                                "has_token": t is not None,
                                "token_expires_at": (
                                    getattr(t, "expires_at", None) if t else None
                                ),
                                "current_time": now,
                                "token_expired": (
                                    getattr(t, "expires_at", 0) < now if t else None
                                ),
                            }
                        },
                    )

                    # Always attempt refresh on 401, regardless of expiry time
                    # Spotify may revoke tokens or have clock skew
                    try:
                        logger.info(
                            "🎵 SPOTIFY CLIENT: Refreshing tokens",
                            extra={"meta": {"user_id": self.user_id}},
                        )
                        await self._refresh_tokens()
                        access_token = await self._get_valid_access_token()
                        headers["Authorization"] = f"Bearer {access_token}"
                        logger.info(
                            "🎵 SPOTIFY CLIENT: Token refresh successful, retrying request",
                            extra={"meta": {"user_id": self.user_id}},
                        )
                        continue  # Retry with new token
                    except SpotifyAuthError as refresh_error:
                        logger.error(
                            "🎵 SPOTIFY CLIENT: Token refresh failed",
                            extra={
                                "meta": {
                                    "user_id": self.user_id,
                                    "error": str(refresh_error),
                                }
                            },
                        )
                        # Refresh failed - token is invalid, user needs reauth
                        raise SpotifyAuthError("needs_reauth")
                else:
                    logger.error(
                        "🎵 SPOTIFY CLIENT: Giving up after failed refresh attempt",
                        extra={"meta": {"user_id": self.user_id, "attempt": attempt}},
                    )
                    # Already attempted refresh on first attempt, give up
                    raise SpotifyAuthError("needs_reauth")

            if r.status_code == 403:
                logger.warning(
                    "🎵 SPOTIFY CLIENT: 403 Forbidden - Premium required or other permission issue",
                    extra={
                        "meta": {
                            "user_id": self.user_id,
                            "attempt": attempt,
                            "method": method,
                            "path": path,
                            "status_code": r.status_code,
                        }
                    },
                )
                # Premium required or other forbidden reason
                raise SpotifyPremiumRequiredError("premium_required")

            # Retry on server errors
            if r.status_code >= 500 and attempt < 3:
                logger.warning(
                    "🎵 SPOTIFY CLIENT: Server error, retrying",
                    extra={
                        "meta": {
                            "user_id": self.user_id,
                            "attempt": attempt,
                            "method": method,
                            "path": path,
                            "status_code": r.status_code,
                            "retry_delay": 0.2 * attempt,
                        }
                    },
                )
                await asyncio.sleep(0.2 * attempt)
                continue

            # Record circuit state and handle backoff
            if r.status_code >= 500:
                logger.warning(
                    "🎵 SPOTIFY CLIENT: Recording failure for circuit breaker",
                    extra={
                        "meta": {"user_id": self.user_id, "status_code": r.status_code}
                    },
                )
                self._record_failure()
            else:
                logger.info(
                    "🎵 SPOTIFY CLIENT: Request successful, clearing backoff",
                    extra={
                        "meta": {
                            "user_id": self.user_id,
                            "status_code": r.status_code,
                            "attempt": attempt,
                        }
                    },
                )
                self._record_success()
                # Clear backoff on successful response
                self._budget_manager.clear_backoff()

            logger.info(
                "🎵 SPOTIFY CLIENT: Returning response",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "method": method,
                        "path": path,
                        "status_code": r.status_code,
                        "final_attempt": attempt,
                    }
                },
            )
            return r

    # ------------------------------------------------------------------
    # Minimal helper to return a fresh access token string for SDK use
    # ------------------------------------------------------------------
    async def _bearer_token_only(self) -> str:
        """Return a valid access token string without performing an API call.

        Raises RuntimeError("not_connected") if no token, or RuntimeError("needs_reauth")
        if refresh is required but fails.
        """
        # Use underlying DAO directly to avoid circular imports
        from app.auth_store_tokens import get_token

        t = await get_token(self.user_id, "spotify")
        if not t:
            raise RuntimeError("not_connected")
        now = int(time.time())
        if t.expires_at <= now:
            # Try to refresh via OAuth helper
            # Call compat method so tests can patch it
            result = await self._refresh_access_token()
            new = SpotifyTokens(
                access_token=result.get("access_token", ""),
                refresh_token=t.refresh_token,
                expires_at=float(result.get("expires_at", 0) or 0),
                scope=getattr(t, "scopes", None),
            )
            await self._store_tokens(new)
            return new.access_token
        return t.access_token

    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open."""
        state = self._circuit_breaker_state
        if state["failures"] >= 5:
            # Open circuit if 5+ failures in last 60 seconds
            if time.time() - state["last_failure"] < 60.0:
                return True
            else:
                # Reset circuit after 60 seconds
                state["failures"] = 0
        return False

    def _record_success(self) -> None:
        """Record successful request for circuit breaker."""
        self._circuit_breaker_state["failures"] = 0

    def _record_failure(self) -> None:
        """Record failed request for circuit breaker."""
        state = self._circuit_breaker_state
        state["failures"] += 1
        state["last_failure"] = time.time()

    # ------------------------------------------------------------------
    # Spotify Web API methods
    # ------------------------------------------------------------------

    async def get_currently_playing(self) -> dict[str, Any] | None:
        """Get the user's currently playing track (raw proxy semantics)."""
        log_spotify_operation(
            "get_currently_playing_start",
            self.user_id,
            {
                "message": "Starting get_currently_playing request",
                "method": "get_currently_playing",
                "endpoint": "/me/player",
            },
        )

        try:
            r = await self._proxy_request(method="GET", path="/me/player")

            log_spotify_operation(
                "get_currently_playing_response",
                self.user_id,
                {
                    "message": "Received response from get_currently_playing",
                    "status_code": r.status_code,
                    "has_content": r.text is not None and len(r.text) > 0,
                    "content_length": len(r.text) if r.text else 0,
                },
            )

            if r.status_code == 204:
                log_spotify_operation(
                    "get_currently_playing_no_content",
                    self.user_id,
                    {
                        "message": "No content (204) - nothing currently playing",
                        "status_code": 204,
                    },
                )
                return None

            if r.status_code != 200:
                log_spotify_operation(
                    "get_currently_playing_error",
                    self.user_id,
                    {
                        "message": f"Error response from get_currently_playing: {r.status_code}",
                        "status_code": r.status_code,
                        "response_text": r.text[:500] if r.text else None,
                        "level": "warning",
                    },
                    level="warning",
                )
                return None

            data = r.json()
            log_spotify_operation(
                "get_currently_playing_success",
                self.user_id,
                {
                    "message": "Successfully retrieved currently playing data",
                    "has_data": data is not None,
                    "data_keys": list(data.keys()) if isinstance(data, dict) else None,
                    "is_playing": (
                        data.get("is_playing") if isinstance(data, dict) else None
                    ),
                    "has_item": "item" in data if isinstance(data, dict) else False,
                },
            )

            return data

        except Exception as e:
            log_spotify_operation(
                "get_currently_playing_exception",
                self.user_id,
                {
                    "message": "Exception in get_currently_playing",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "level": "error",
                },
                level="error",
            )
            raise

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get available playback devices (raw proxy semantics)."""
        logger.info(
            "🎵 SPOTIFY CLIENT: get_devices called",
            extra={"meta": {"user_id": self.user_id}},
        )

        try:
            logger.info(
                "🎵 SPOTIFY CLIENT: About to call _proxy_request",
                extra={"meta": {"user_id": self.user_id}},
            )
            r = await self._proxy_request(method="GET", path="/me/player/devices")
            logger.info(
                "🎵 SPOTIFY CLIENT: _proxy_request completed",
                extra={"meta": {"user_id": self.user_id, "status_code": r.status_code}},
            )
            try:
                hdrs = dict(getattr(r, "headers", {}) or {})
            except Exception:
                hdrs = {}
            logger.info(
                "🎵 SPOTIFY CLIENT: get_devices API response",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "status_code": r.status_code,
                        "headers": hdrs,
                        "response_time": getattr(r, "_response_time", None),
                    }
                },
            )

            if r.status_code != 200:
                logger.warning(
                    "🎵 SPOTIFY CLIENT: get_devices non-200 response",
                    extra={
                        "meta": {
                            "user_id": self.user_id,
                            "status_code": r.status_code,
                            "response_text": r.text[:500] if r.text else None,
                        }
                    },
                )
                return []

            data = r.json() or {}
            devices = data.get("devices", [])

            logger.info(
                "🎵 SPOTIFY CLIENT: get_devices success",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "device_count": len(devices),
                        "devices": devices,
                    }
                },
            )

            return devices
        except Exception as e:
            logger.error(
                "🎵 SPOTIFY CLIENT: get_devices error",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                },
            )
            raise

    async def transfer_playback(self, device_id: str, play: bool = True) -> bool:
        """Transfer playback to a specific device (raw proxy)."""
        r = await self._proxy_request(
            method="PUT", path="/me/player", json_body={"device_ids": [device_id], "play": play}
        )
        return r.status_code in (200, 202, 204)

    async def play(
        self, uris: list[str] | None = None, context_uri: str | None = None
    ) -> bool:
        """Start or resume playback (raw proxy)."""
        body = {}
        if uris:
            body["uris"] = uris
        if context_uri:
            body["context_uri"] = context_uri
        r = await self._proxy_request(method="PUT", path="/me/player/play", json_body=body or None)
        # Promote 429 to a typed error so route can propagate Retry-After
        if r.status_code == 429:
            retry_after = None
            try:
                retry_after = int((r.headers or {}).get("Retry-After", "0") or 0)
            except Exception:
                retry_after = None
            raise SpotifyRateLimitedError(retry_after)
        return r.status_code in (200, 202, 204)

    async def pause(self) -> bool:
        """Pause playback (raw proxy)."""
        r = await self._proxy_request(method="PUT", path="/me/player/pause")
        return r.status_code in (200, 202, 204)

    async def next_track(self) -> bool:
        """Skip to next track (raw proxy)."""
        r = await self._proxy_request(method="POST", path="/me/player/next")
        return r.status_code in (200, 202, 204)

    async def previous_track(self) -> bool:
        """Skip to previous track (raw proxy)."""
        r = await self._proxy_request(method="POST", path="/me/player/previous")
        return r.status_code in (200, 202, 204)

    async def set_volume(self, volume_percent: int) -> bool:
        """Set playback volume (raw proxy)."""
        volume = max(0, min(100, volume_percent))
        r = await self._proxy_request(
            method="PUT", path="/me/player/volume", params={"volume_percent": volume}
        )
        return r.status_code in (200, 202, 204)

    async def get_queue(self) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        """Get current queue information."""
        response = await self._request("GET", "/me/player/queue")
        if response.status_code != 200:
            return None, []

        data = response.json()
        return data.get("currently_playing"), data.get("queue", [])

    async def get_recommendations(
        self,
        *,
        seed_tracks: list[str] | None = None,
        seed_artists: list[str] | None = None,
        seed_genres: list[str] | None = None,
        target_energy: float | None = None,
        target_tempo: float | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Get track recommendations."""
        params = {"limit": max(1, min(100, limit))}

        if seed_tracks:
            # Convert track URIs to IDs if needed
            track_ids = [t.split(":")[-1] for t in seed_tracks[:5]]
            params["seed_tracks"] = ",".join(track_ids)

        if seed_artists:
            artist_ids = [a.split(":")[-1] for a in seed_artists[:5]]
            params["seed_artists"] = ",".join(artist_ids)

        if seed_genres:
            params["seed_genres"] = ",".join(seed_genres[:5])

        if target_energy is not None:
            params["target_energy"] = max(0.0, min(1.0, float(target_energy)))

        if target_tempo is not None:
            params["target_tempo"] = float(target_tempo)

        response = await self._request("GET", "/recommendations", params=params)
        if response.status_code != 200:
            return []

        data = response.json()
        return data.get("tracks", [])

    async def search_tracks(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search for tracks."""
        params = {"q": query, "type": "track", "limit": max(1, min(50, limit))}

        response = await self._request("GET", "/search", params=params)
        if response.status_code != 200:
            return []

        data = response.json()
        tracks = data.get("tracks", {}).get("items", [])
        return tracks

    async def get_user_profile(self) -> dict[str, Any] | None:
        """Get current user's profile."""
        response = await self._request("GET", "/me")
        if response.status_code != 200:
            return None
        return response.json()

    async def get_track(self, track_id: str) -> dict[str, Any] | None:
        """Get track information by ID."""
        # Handle both full URI and just ID
        track_id = track_id.split(":")[-1]
        response = await self._request("GET", f"/tracks/{track_id}")
        if response.status_code != 200:
            return None
        return response.json()
