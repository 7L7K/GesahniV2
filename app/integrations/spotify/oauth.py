from __future__ import annotations

import base64
import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from ...models.third_party_tokens import ThirdPartyToken

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
        # Generate cryptographically secure verifier (43-128 chars)
        verifier = secrets.token_urlsafe(64)

        # Create SHA256 hash of verifier
        verifier_bytes = verifier.encode('utf-8')
        challenge_bytes = hashlib.sha256(verifier_bytes).digest()

        # Base64url encode the challenge
        challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')

        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        return SpotifyPKCE(
            verifier=verifier,
            challenge=challenge,
            state=state,
            created_at=time.time()
        )

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

    async def exchange_code_for_tokens(self, code: str, pkce: SpotifyPKCE) -> dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
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

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(token_url, data=data, headers=headers)

            if response.status_code != 200:
                raise SpotifyOAuthError(f"Token exchange failed: {response.status_code} {response.text}")

            token_data = response.json()

            # Add expiration timestamp for convenience
            expires_in = token_data.get("expires_in", 3600)
            token_data["expires_at"] = int(time.time()) + expires_in

            return token_data

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        """Refresh an access token using the refresh token."""
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

        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
            response = await client.post(token_url, data=data, headers=headers)

            if response.status_code != 200:
                raise SpotifyOAuthError(f"Token refresh failed: {response.status_code} {response.text}")

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
_pkce_store: dict[str, SpotifyPKCE] = {}


def store_pkce_challenge(session_id: str, pkce: SpotifyPKCE) -> None:
    """Store PKCE challenge in session storage."""
    _pkce_store[session_id] = pkce


def get_pkce_challenge(session_id: str) -> SpotifyPKCE | None:
    """Retrieve PKCE challenge from session storage."""
    return _pkce_store.get(session_id)


def clear_pkce_challenge(session_id: str) -> None:
    """Remove PKCE challenge from session storage."""
    _pkce_store.pop(session_id, None)


def cleanup_expired_pkce_challenges(max_age_seconds: int = 600) -> None:
    """Clean up expired PKCE challenges from storage."""
    now = time.time()
    expired = [
        session_id for session_id, pkce in _pkce_store.items()
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
        pkce = SpotifyOAuth().generate_pkce()
        # Return (state, challenge, verifier)
        return pkce.state, pkce.challenge, pkce.verifier

    def build(self, *, state: str, code_challenge: str) -> str:
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
        return f"https://accounts.spotify.com/authorize?{urlencode(params)}"


make_authorize_url = _MakeAuthorizeUrl()


@with_span("spotify.exchange_code")
async def exchange_code(code: str, code_verifier: str) -> ThirdPartyToken:
    """Exchange an authorization code for token data and return a simple dict.

    The returned dict contains at least: access_token, refresh_token (opt), scope, expires_at
    """
    oauth = SpotifyOAuth()
    td = await oauth.exchange_code_for_tokens(code, SpotifyPKCE(verifier=code_verifier, challenge="", state="", created_at=time.time()))
    now = int(time.time())
    expires_at = int(td.get("expires_at", now + int(td.get("expires_in", 3600))))
    return ThirdPartyToken(
        id=f"spotify:{secrets.token_hex(8)}",
        user_id="<set by caller>",
        provider="spotify",
        access_token=td.get("access_token", ""),
        refresh_token=td.get("refresh_token"),
        scope=td.get("scope"),
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
