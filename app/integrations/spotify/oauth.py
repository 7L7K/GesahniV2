from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from ...models.third_party_tokens import ThirdPartyToken

logger = logging.getLogger(__name__)


def log_spotify_oauth(operation: str, details: dict = None, level: str = "info"):
    """Enhanced Spotify OAuth logging."""
    details = details or {}
    log_data = {
        "operation": operation,
        "component": "spotify_oauth",
        "timestamp": time.time(),
        **details,
    }

    if level == "debug":
        logger.debug(f"🔐 SPOTIFY OAUTH {operation.upper()}", extra={"meta": log_data})
    elif level == "warning":
        logger.warning(
            f"🔐 SPOTIFY OAUTH {operation.upper()}", extra={"meta": log_data}
        )
    elif level == "error":
        logger.error(f"🔐 SPOTIFY OAUTH {operation.upper()}", extra={"meta": log_data})
    else:
        logger.info(f"🔐 SPOTIFY OAUTH {operation.upper()}", extra={"meta": log_data})


# telemetry span decorator fallback
try:
    from ...telemetry import with_span
except Exception:  # pragma: no cover - telemetry optional

    def with_span(name: str):
        def _decorator(f):
            return f

        return _decorator


@dataclass
class SpotifyPKCE:
    """PKCE challenge-response data for Spotify OAuth flow."""

    verifier: str
    challenge: str
    state: str
    created_at: float


class SpotifyOAuth:
    """Spotify OAuth 2.0 with PKCE flow implementation."""

    def __init__(self) -> None:
        self.client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
        self.redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI", "").strip()
        self.scopes = os.getenv("SPOTIFY_SCOPES", self._default_scopes()).strip()

        if not self.client_id or not self.client_secret:
            raise ValueError("SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET are required")

    def _default_scopes(self) -> str:
        """Return minimal but future-proof scopes for Spotify integration."""
        return "user-read-playback-state user-modify-playback-state streaming playlist-read-private playlist-modify-private"

    def generate_pkce(self) -> SpotifyPKCE:
        """Generate PKCE verifier, challenge, and state for OAuth flow."""
        logger.info("🎵 SPOTIFY PKCE: Generating PKCE challenge...")

        # Generate cryptographically secure verifier (43-128 chars)
        verifier = secrets.token_urlsafe(64)
        logger.debug(
            "🎵 SPOTIFY PKCE: Generated verifier",
            extra={"meta": {"verifier_length": len(verifier)}},
        )

        # Create SHA256 hash of verifier
        verifier_bytes = verifier.encode("utf-8")
        challenge_bytes = hashlib.sha256(verifier_bytes).digest()

        # Base64url encode the challenge
        challenge = (
            base64.urlsafe_b64encode(challenge_bytes).decode("utf-8").rstrip("=")
        )

        logger.debug(
            "🎵 SPOTIFY PKCE: Generated challenge",
            extra={
                "meta": {"challenge_length": len(challenge), "hash_algorithm": "SHA256"}
            },
        )

        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        logger.debug(
            "🎵 SPOTIFY PKCE: Generated state",
            extra={"meta": {"state_length": len(state)}},
        )

        pkce_data = SpotifyPKCE(
            verifier=verifier, challenge=challenge, state=state, created_at=time.time()
        )

        logger.info(
            "🎵 SPOTIFY PKCE: PKCE generation complete",
            extra={
                "meta": {
                    "verifier_length": len(verifier),
                    "challenge_length": len(challenge),
                    "state_length": len(state),
                    "created_at": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(pkce_data.created_at)
                    ),
                }
            },
        )

        return pkce_data

    def get_authorization_url(self, pkce: SpotifyPKCE) -> str:
        """Generate Spotify authorization URL with PKCE challenge."""
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": pkce.state,
            "code_challenge": pkce.challenge,
            "code_challenge_method": "S256",  # Use SHA256 for security
            "show_dialog": "true",
        }
        return f"https://accounts.spotify.com/authorize?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, pkce: SpotifyPKCE
    ) -> dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        log_spotify_oauth(
            "exchange_code_start",
            {
                "message": "Starting code exchange for tokens",
                "code_length": len(code) if code else 0,
                "pkce_state": pkce.state[:8] + "..." if pkce.state else None,
            },
        )

        token_url = "https://accounts.spotify.com/api/token"

        # Prepare token exchange data
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code_verifier": pkce.verifier,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        # In test mode, mint deterministic tokens without calling Spotify
        test_mode_env = os.getenv("SPOTIFY_TEST_MODE", "0")
        # Treat pytest runs as test mode as well so refresh/exchange can be deterministic
        is_test_mode = test_mode_env == "1" or bool(
            os.getenv("PYTEST_RUNNING") or os.getenv("PYTEST_CURRENT_TEST")
        )
        is_fake_code = code == "fake"

        log_spotify_oauth(
            "test_mode_check",
            {
                "message": "Checking test mode configuration",
                "test_mode_env": test_mode_env,
                "is_test_mode": is_test_mode,
                "code": code[:8] + "..." if code else None,
                "is_fake_code": is_fake_code,
                "condition_met": is_test_mode and is_fake_code,
            },
        )

        if is_test_mode and is_fake_code:
            log_spotify_oauth(
                "using_test_mode",
                {
                    "message": "Using test mode - returning fake tokens",
                    "code": code[:8] + "..." if code else None,
                },
            )
            now = int(time.time())
            fake_tokens = {
                "access_token": f"B{secrets.token_hex(16)}",  # Start with 'B' to pass validation
                "refresh_token": f"A{secrets.token_hex(16)}",  # Start with 'A' and ensure length > 10
                "scope": self.scopes,
                "expires_in": 3600,
                "expires_at": now + 3600,
            }
            log_spotify_oauth(
                "test_tokens_generated",
                {
                    "message": "Test tokens generated successfully",
                    "access_token_length": len(fake_tokens["access_token"]),
                    "refresh_token_length": len(fake_tokens["refresh_token"]),
                    "expires_at": fake_tokens["expires_at"],
                },
            )
            return fake_tokens

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0)
        ) as client:
            response = await client.post(token_url, data=data, headers=headers)

            if response.status_code != 200:
                raise SpotifyOAuthError(
                    f"Token exchange failed: {response.status_code} {response.text}"
                )

            token_data = response.json()

            # Add expiration timestamp for convenience
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = int(time.time()) + expires_in

            return token_data

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an access token using the refresh token."""
        # In test mode, return deterministic fake refreshed tokens so tests
        # that invoke refresh don't call out to Spotify and can validate updates.
        if os.getenv("SPOTIFY_TEST_MODE", "0") == "1":
            now = int(time.time())
            return {
                "access_token": f"B{secrets.token_hex(16)}",
                "refresh_token": refresh_token,
                "scope": self.scopes,
                "expires_in": 3600,
                "expires_at": now + 3600,
            }
        token_url = "https://accounts.spotify.com/api/token"

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
        }

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0)
        ) as client:
            response = await client.post(token_url, data=data, headers=headers)

            if response.status_code != 200:
                raise SpotifyOAuthError(
                    f"Token refresh failed: {response.status_code} {response.text}"
                )

            token_data = response.json()

            # Add expiration timestamp and preserve original refresh token if not provided
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = int(time.time()) + expires_in

            # Spotify may not return a new refresh token
            if "refresh_token" not in token_data:
                token_data["refresh_token"] = refresh_token

            return token_data

    def is_pkce_valid(self, pkce: SpotifyPKCE, max_age_seconds: int = 600) -> bool:
        """Check if PKCE data is still valid (not expired)."""
        return (time.time() - pkce.created_at) < max_age_seconds


class SpotifyOAuthError(Exception):
    """Exception raised for Spotify OAuth errors."""

    pass


# Session storage for PKCE challenges (in production, use Redis or database)
# Now stores multiple challenges per session to handle multiple concurrent requests
_pkce_store: dict[str, list[SpotifyPKCE]] = {}


def store_pkce_challenge(session_id: str, pkce: SpotifyPKCE) -> None:
    """Store PKCE challenge in session storage."""
    if session_id not in _pkce_store:
        _pkce_store[session_id] = []
    _pkce_store[session_id].append(pkce)


def get_pkce_challenge_by_state(session_id: str, state: str) -> SpotifyPKCE | None:
    """Retrieve PKCE challenge from session storage by state."""
    if session_id not in _pkce_store:
        return None

    # Find challenge with matching state (most recent first)
    challenges = _pkce_store[session_id]
    for pkce in reversed(challenges):
        if pkce.state == state:
            return pkce
    return None


def get_pkce_challenge(session_id: str) -> SpotifyPKCE | None:
    """Retrieve most recent PKCE challenge from session storage."""
    if session_id not in _pkce_store:
        return None
    return _pkce_store[session_id][-1] if _pkce_store[session_id] else None


def clear_pkce_challenge_by_state(session_id: str, state: str) -> None:
    """Remove specific PKCE challenge from session storage by state."""
    if session_id in _pkce_store:
        challenges = _pkce_store[session_id]
        _pkce_store[session_id] = [pkce for pkce in challenges if pkce.state != state]
        # Clean up empty lists
        if not _pkce_store[session_id]:
            del _pkce_store[session_id]


def clear_pkce_challenge(session_id: str) -> None:
    """Remove all PKCE challenges for a session."""
    _pkce_store.pop(session_id, None)


def cleanup_expired_pkce_challenges(max_age_seconds: int = 600) -> None:
    """Clean up expired PKCE challenges from storage."""
    now = time.time()
    expired = [
        session_id
        for session_id, pkce in _pkce_store.items()
        if (now - pkce.created_at) >= max_age_seconds
    ]
    for session_id in expired:
        del _pkce_store[session_id]


# Convenience constants used by the API layer
STATE_KEY = "spotify_oauth_state"
PKCE_VERIFIER_KEY = "spotify_pkce_verifier"


class _MakeAuthorizeUrl:
    """Helper object that mirrors the minimal interface expected by routes.

    Methods:
      - prepare_pkce() -> (state, code_challenge, code_verifier)
      - build(state, code_challenge) -> authorization_url
    """

    async def prepare_pkce(self) -> tuple[str, str, str]:
        logger.info("🎵 SPOTIFY AUTH URL: Preparing PKCE for authorization URL...")
        pkce = SpotifyOAuth().generate_pkce()
        logger.info(
            "🎵 SPOTIFY AUTH URL: PKCE prepared",
            extra={
                "meta": {
                    "state_length": len(pkce.state),
                    "challenge_length": len(pkce.challenge),
                    "verifier_length": len(pkce.verifier),
                }
            },
        )
        # Return (state, challenge, verifier)
        return pkce.state, pkce.challenge, pkce.verifier

    def build(self, *, state: str, code_challenge: str) -> str:
        logger.info("🎵 SPOTIFY AUTH URL: Building authorization URL...")
        client_id = os.getenv("SPOTIFY_CLIENT_ID", "")
        redirect = os.getenv("SPOTIFY_REDIRECT_URI", "")
        scopes = os.getenv(
            "SPOTIFY_SCOPES",
            "user-read-playback-state user-modify-playback-state streaming playlist-read-private playlist-modify-private",
        )

        params = {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect,
            "scope": scopes,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "show_dialog": "true",
        }

        auth_url = f"https://accounts.spotify.com/authorize?{urlencode(params)}"

        logger.info(
            "🎵 SPOTIFY AUTH URL: Authorization URL built",
            extra={
                "meta": {
                    "auth_url_length": len(auth_url),
                    "client_id_configured": bool(client_id),
                    "redirect_uri_configured": bool(redirect),
                    "scopes": scopes,
                    "state_provided": bool(state),
                    "code_challenge_provided": bool(code_challenge),
                    "pkce_method": "S256",
                }
            },
        )

        return auth_url


make_authorize_url = _MakeAuthorizeUrl()


@with_span("spotify.exchange_code")
async def exchange_code(code: str, code_verifier: str) -> ThirdPartyToken:
    """Exchange an authorization code for token data and return a simple dict.

    The returned dict contains at least: access_token, refresh_token (opt), scope, expires_at
    """
    logger.info(
        "🎵 SPOTIFY EXCHANGE: Starting code exchange...",
        extra={
            "meta": {
                "code_length": len(code) if code else 0,
                "code_verifier_length": len(code_verifier) if code_verifier else 0,
            }
        },
    )

    oauth = SpotifyOAuth()
    pkce_for_exchange = SpotifyPKCE(
        verifier=code_verifier, challenge="", state="", created_at=time.time()
    )

    logger.info("🎵 SPOTIFY EXCHANGE: Calling Spotify token endpoint...")
    td = await oauth.exchange_code_for_tokens(code, pkce_for_exchange)

    logger.info(
        "🎵 SPOTIFY EXCHANGE: Token response received",
        extra={
            "meta": {
                "response_keys": list(td.keys()) if td else [],
                "has_access_token": bool(td.get("access_token")),
                "has_refresh_token": bool(td.get("refresh_token")),
                "token_type": td.get("token_type", "unknown"),
                "expires_in": td.get("expires_in", 0),
                "scope": td.get("scope", "unknown"),
            }
        },
    )

    now = int(time.time())
    expires_at = int(td.get("expires_at", now + int(td.get("expires_in", 3600))))

    token_data = ThirdPartyToken(
        id=f"spotify:{secrets.token_hex(8)}",
        user_id="<set by caller>",
        provider="spotify",
        access_token=td.get("access_token", ""),
        refresh_token=td.get("refresh_token"),
        scopes=td.get("scope"),
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )

    logger.info(
        "🎵 SPOTIFY EXCHANGE: Token data prepared",
        extra={
            "meta": {
                "token_id": token_data.id,
                "access_token_length": len(token_data.access_token),
                "has_refresh_token": bool(token_data.refresh_token),
                "refresh_token_length": (
                    len(token_data.refresh_token) if token_data.refresh_token else 0
                ),
                "expires_at_timestamp": expires_at,
                "expires_at_formatted": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(expires_at)
                ),
                "seconds_until_expiry": expires_at - now,
            }
        },
    )

    return token_data
