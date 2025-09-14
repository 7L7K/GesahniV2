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
        self.user_id = user_id
        self.oauth = SpotifyOAuth()
        self._circuit_breaker_state = {"failures": 0, "last_failure": 0.0}
        self._budget_manager = get_spotify_budget_manager(user_id)

    # ------------------------------------------------------------------
    # Token management with unified storage
    # ------------------------------------------------------------------

    async def _get_tokens(self) -> SpotifyTokens | None:
        """Retrieve tokens from unified token store."""
        logger.info(
            "🎵 SPOTIFY CLIENT: _get_tokens called",
            extra={"meta": {"user_id": self.user_id, "provider": "spotify"}},
        )

        token = await get_token(self.user_id, "spotify")

        logger.info(
            "🎵 SPOTIFY CLIENT: _get_tokens result",
            extra={
                "meta": {
                    "user_id": self.user_id,
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
                }
            },
        )

        if not token:
            logger.warning(
                "🎵 SPOTIFY CLIENT: No token found in store",
                extra={"meta": {"user_id": self.user_id, "provider": "spotify"}},
            )
            return None

        return SpotifyTokens(
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_at=token.expires_at,
            scope=token.scope,
        )

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
        except Exception:
            pass

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

    async def disconnect(self) -> bool:
        """Disconnect by marking tokens as invalid."""
        return await mark_invalid(self.user_id, "spotify")

    async def _get_valid_access_token(self) -> str:
        """Get a valid access token, refreshing if necessary."""
        logger.info(
            "🎵 SPOTIFY CLIENT: _get_valid_access_token called",
            extra={"meta": {"user_id": self.user_id, "provider": "spotify"}},
        )

        # Use the new robust token service
        from ...auth_store_tokens import get_valid_token_with_auto_refresh

        logger.info(
            "🎵 SPOTIFY CLIENT: Calling get_valid_token_with_auto_refresh",
            extra={
                "meta": {
                    "user_id": self.user_id,
                    "provider": "spotify",
                    "force_refresh": False,
                }
            },
        )

        token = await get_valid_token_with_auto_refresh(
            self.user_id, "spotify", force_refresh=False
        )

        logger.info(
            "🎵 SPOTIFY CLIENT: get_valid_token_with_auto_refresh result",
            extra={
                "meta": {
                    "user_id": self.user_id,
                    "provider": "spotify",
                    "has_token": token is not None,
                    "token_type": type(token).__name__ if token else None,
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
                }
            },
        )

        if not token:
            logger.error(
                "🎵 SPOTIFY CLIENT: No valid Spotify tokens found",
                extra={"meta": {"user_id": self.user_id, "provider": "spotify"}},
            )
            raise SpotifyAuthError("No valid Spotify tokens found")

        # Double-check token is not expired (additional safety)
        logger.info(
            "🎵 SPOTIFY CLIENT: Checking token expiry",
            extra={
                "meta": {
                    "user_id": self.user_id,
                    "provider": "spotify",
                    "expires_at": getattr(token, "expires_at", None),
                    "current_time": int(time.time()),
                    "is_expired_60s": getattr(token, "is_expired", lambda x: True)(60),
                }
            },
        )

        if token.is_expired(60):  # 1 minute buffer
            logger.warning(
                "🎵 SPOTIFY CLIENT: Token expired, forcing refresh",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "provider": "spotify",
                        "expires_at": getattr(token, "expires_at", None),
                    }
                },
            )

            # Force refresh if still expired
            token = await get_valid_token_with_auto_refresh(
                self.user_id, "spotify", force_refresh=True
            )

            logger.info(
                "🎵 SPOTIFY CLIENT: Force refresh result",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "provider": "spotify",
                        "has_token_after_refresh": token is not None,
                    }
                },
            )

            if not token:
                logger.error(
                    "🎵 SPOTIFY CLIENT: Failed to refresh Spotify token",
                    extra={"meta": {"user_id": self.user_id, "provider": "spotify"}},
                )
                raise SpotifyAuthError("Failed to refresh Spotify token")

        logger.info(
            "🎵 SPOTIFY CLIENT: Returning valid access token",
            extra={
                "meta": {
                    "user_id": self.user_id,
                    "provider": "spotify",
                    "token_length": (
                        len(getattr(token, "access_token", "")) if token else 0
                    ),
                }
            },
        )

        return token.access_token

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
            except Exception:
                pass

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
                except Exception:
                    pass
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
                except Exception:
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
                except Exception:
                    pass

                # Only attempt refresh on first attempt to avoid infinite loops
                if attempt == 1:
                    logger.info(
                        "🎵 SPOTIFY CLIENT: Attempting token refresh on 401",
                        extra={"meta": {"user_id": self.user_id, "attempt": attempt}},
                    )

                    # Check if token needs refresh based on expiry
                    from ...auth_store_tokens import get_token as _get_token

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
        from ...auth_store_tokens import get_token as _get_token

        t = await _get_token(self.user_id, "spotify")
        if not t:
            raise RuntimeError("not_connected")
        now = int(time.time())
        if t.expires_at <= now:
            # Try to refresh via OAuth helper
            try:
                new = await self._refresh_tokens()
                return new.access_token
            except SpotifyAuthError:
                raise RuntimeError("needs_reauth")
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
        r = await self._proxy_request("GET", "/me/player")
        if r.status_code == 204:
            return None
        if r.status_code != 200:
            return None
        return r.json()

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get available playback devices (raw proxy semantics)."""
        logger.info(
            "🎵 SPOTIFY CLIENT: get_devices called",
            extra={"meta": {"user_id": self.user_id}},
        )

        try:
            r = await self._proxy_request("GET", "/me/player/devices")
            logger.info(
                "🎵 SPOTIFY CLIENT: get_devices API response",
                extra={
                    "meta": {
                        "user_id": self.user_id,
                        "status_code": r.status_code,
                        "headers": dict(r.headers),
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
            "PUT", "/me/player", json_body={"device_ids": [device_id], "play": play}
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
        r = await self._proxy_request("PUT", "/me/player/play", json_body=body or None)
        return r.status_code in (200, 202, 204)

    async def pause(self) -> bool:
        """Pause playback (raw proxy)."""
        r = await self._proxy_request("PUT", "/me/player/pause")
        return r.status_code in (200, 202, 204)

    async def next_track(self) -> bool:
        """Skip to next track (raw proxy)."""
        r = await self._proxy_request("POST", "/me/player/next")
        return r.status_code in (200, 202, 204)

    async def previous_track(self) -> bool:
        """Skip to previous track (raw proxy)."""
        r = await self._proxy_request("POST", "/me/player/previous")
        return r.status_code in (200, 202, 204)

    async def set_volume(self, volume_percent: int) -> bool:
        """Set playback volume (raw proxy)."""
        volume = max(0, min(100, volume_percent))
        r = await self._proxy_request(
            "PUT", "/me/player/volume", params={"volume_percent": volume}
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
