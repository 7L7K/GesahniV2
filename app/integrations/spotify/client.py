from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from time import perf_counter

from ...metrics import SPOTIFY_REQUESTS, SPOTIFY_429, SPOTIFY_REFRESH, SPOTIFY_LATENCY

from ...auth_store_tokens import get_token, upsert_token, mark_invalid
from ...budget import get_budget_state
from ...http_utils import json_request
from ...models.third_party_tokens import ThirdPartyToken
from .oauth import SpotifyOAuth, SpotifyOAuthError


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

    # ------------------------------------------------------------------
    # Token management with unified storage
    # ------------------------------------------------------------------

    async def _get_tokens(self) -> SpotifyTokens | None:
        """Retrieve tokens from unified token store."""
        token = await get_token(self.user_id, "spotify")
        if not token:
            return None

        return SpotifyTokens(
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_at=token.expires_at,
            scope=token.scope
        )

    async def _store_tokens(self, tokens: SpotifyTokens) -> None:
        """Store tokens in unified token store."""
        token = ThirdPartyToken(
            user_id=self.user_id,
            provider="spotify",
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            scope=tokens.scope,
            expires_at=tokens.expires_at
        )
        await upsert_token(token)

    async def _refresh_tokens(self) -> SpotifyTokens:
        """Refresh access token using refresh token."""
        current_tokens = await self._get_tokens()
        if not current_tokens or not current_tokens.refresh_token:
            raise SpotifyAuthError("No refresh token available")

        try:
            token_data = await self.oauth.refresh_access_token(current_tokens.refresh_token)

            new_tokens = SpotifyTokens(
                access_token=token_data["access_token"],
                refresh_token=token_data.get("refresh_token", current_tokens.refresh_token),
                expires_at=int(token_data["expires_at"]),
                scope=token_data.get("scope", current_tokens.scope)
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
        tokens = await self._get_tokens()
        if not tokens:
            raise SpotifyAuthError("No Spotify tokens found")

        # Check if token is expired or will expire soon (within 5 minutes)
        if time.time() >= (tokens.expires_at - 300):
            tokens = await self._refresh_tokens()

        return tokens.access_token

    # ------------------------------------------------------------------
    # Budget and timeout support
    # ------------------------------------------------------------------

    def _check_budget(self) -> None:
        """Check if user is within budget limits."""
        budget_state = get_budget_state(self.user_id)
        if not budget_state.get("escalate_allowed", True):
            raise SpotifyAuthError("Budget limit exceeded for Spotify operations")

    def _get_timeout(self) -> float:
        """Get appropriate timeout based on budget and router settings."""
        # Respect ROUTER_BUDGET_MS environment variable
        router_budget_ms = float(os.getenv("ROUTER_BUDGET_MS", "30000"))  # 30 seconds default

        # Use a portion of the router budget for Spotify calls
        spotify_timeout = min(router_budget_ms / 1000 * 0.8, 30.0)  # 80% of budget, max 30s

        # Check budget state for additional constraints
        budget_state = get_budget_state(self.user_id)
        if budget_state.get("reply_len_target") == "short":
            spotify_timeout = min(spotify_timeout, 10.0)  # Reduce timeout under budget pressure

        return spotify_timeout

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
                    timeout=timeout
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
                            raise SpotifyAuthError("Authentication failed after token refresh")

                    # Handle other errors
                    self._record_failure()
                    raise SpotifyAuthError(f"Spotify API error: {error}")

                # Success - create a mock response object for compatibility
                class MockResponse:
                    status_code = 200

                    def __init__(self, data: Any):
                        self.data = data

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

                raise SpotifyAuthError(f"Request failed after {max_attempts} attempts: {e}")

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
        self._check_budget()
        timeout = self._get_timeout()
        url = f"{self.api_base}{path}"

        # Circuit breaker check
        if self._is_circuit_open():
            raise SpotifyAuthError("Circuit breaker open - too many recent failures")

        access_token = await self._get_valid_access_token()

        headers = {"Authorization": f"Bearer {access_token}"}

        attempt = 0
        while attempt < 3:
            attempt += 1
            async with httpx.AsyncClient(timeout=timeout) as client:
                t0 = perf_counter()
                r = await client.request(method, url, params=params, json=json_body, headers=headers)
                dt = perf_counter() - t0

            # observe metrics
            try:
                SPOTIFY_LATENCY.labels(method, path).observe(dt)
                SPOTIFY_REQUESTS.labels(method, path, str(r.status_code)).inc()
            except Exception:
                pass

            # Handle rate limit explicitly
            if r.status_code == 429:
                try:
                    SPOTIFY_429.labels(path).inc()
                except Exception:
                    pass
                retry_after = None
                try:
                    retry_after = int((r.headers or {}).get("Retry-After", "0") or 0)
                except Exception:
                    retry_after = None
                # Surface a specialized exception for UI
                raise SpotifyRateLimitedError(retry_after, "rate_limited")

            if r.status_code == 401:
                try:
                    SPOTIFY_REFRESH.inc()
                except Exception:
                    pass
                # Try one refresh then retry
                try:
                    await self._refresh_tokens()
                    access_token = await self._get_valid_access_token()
                    headers["Authorization"] = f"Bearer {access_token}"
                    continue
                except SpotifyAuthError:
                    # No refresh possible
                    raise SpotifyAuthError("needs_reauth")

            if r.status_code == 403:
                # Premium required or other forbidden reason
                raise SpotifyPremiumRequiredError("premium_required")

            # Retry on server errors
            if r.status_code >= 500 and attempt < 3:
                await asyncio.sleep(0.2 * attempt)
                continue

            # Record circuit state
            if r.status_code >= 500:
                self._record_failure()
            else:
                self._record_success()

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
        """Get the user's currently playing track."""
        response = await self._request("GET", "/me/player")
        if response.status_code == 204:  # No active playback
            return None
        if response.status_code != 200:
            return None
        return response.json()

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get available playback devices."""
        response = await self._request("GET", "/me/player/devices")
        if response.status_code != 200:
            return []
        data = response.json()
        return data.get("devices", [])

    async def transfer_playback(self, device_id: str, play: bool = True) -> bool:
        """Transfer playback to a specific device."""
        response = await self._request(
            "PUT",
            "/me/player",
            json_body={"device_ids": [device_id], "play": play}
        )
        return response.status_code in (200, 202, 204)

    async def play(self, uris: list[str] | None = None, context_uri: str | None = None) -> bool:
        """Start or resume playback."""
        body = {}
        if uris:
            body["uris"] = uris
        if context_uri:
            body["context_uri"] = context_uri

        response = await self._request("PUT", "/me/player/play", json_body=body if body else None)
        return response.status_code in (200, 202, 204)

    async def pause(self) -> bool:
        """Pause playback."""
        response = await self._request("PUT", "/me/player/pause")
        return response.status_code in (200, 202, 204)

    async def next_track(self) -> bool:
        """Skip to next track."""
        response = await self._request("POST", "/me/player/next")
        return response.status_code in (200, 202, 204)

    async def previous_track(self) -> bool:
        """Skip to previous track."""
        response = await self._request("POST", "/me/player/previous")
        return response.status_code in (200, 202, 204)

    async def set_volume(self, volume_percent: int) -> bool:
        """Set playback volume."""
        volume = max(0, min(100, volume_percent))
        response = await self._request(
            "PUT",
            "/me/player/volume",
            params={"volume_percent": volume}
        )
        return response.status_code in (200, 202, 204)

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
        params = {
            "q": query,
            "type": "track",
            "limit": max(1, min(50, limit))
        }

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
