from __future__ import annotations

import os
import secrets
import logging
from urllib.parse import urlencode

import aiohttp
from fastapi import APIRouter, Request, Response, HTTPException

from ..cookies import set_oauth_state_cookies, clear_oauth_state_cookies
from ..integrations.spotify.oauth import (
    store_pkce_challenge,
    get_pkce_challenge,
    clear_pkce_challenge,
    SpotifyPKCE,
    SpotifyOAuth,
    make_authorize_url,
    exchange_code,
    STATE_KEY,
    PKCE_VERIFIER_KEY,
)
from ..integrations.spotify.client import SpotifyClient
from ..auth_store_tokens import upsert_token
from ..models.third_party_tokens import ThirdPartyToken
from ..deps.user import get_current_user_id, resolve_session_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/spotify")

SPOTIFY_AUTH = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"


def _pkce_challenge() -> SpotifyPKCE:
    """Generate PKCE challenge for OAuth flow."""
    oauth = SpotifyOAuth()
    return oauth.generate_pkce()


@router.get("/connect")
async def spotify_connect(request: Request, user_id: str = get_current_user_id) -> Response:
    """Initiate Spotify OAuth flow with PKCE.

    This route requires authentication; the current user's ID is bound to the
    session and later used to persist tokens. For unauthenticated flows, call
    `resolve_session_id()` and bind tokens to that session after sign-in.
    """
    # Generate PKCE and authorization URL via helper
    state, challenge, verifier = await make_authorize_url.prepare_pkce()

    # Store verifier tied to the session (session id from cookie or resolved)
    sid = resolve_session_id(request=request)
    store_pkce_challenge(sid, SpotifyPKCE(verifier=verifier, challenge=challenge, state=state, created_at=time.time()))

    auth_url = make_authorize_url.build(state=state, code_challenge=challenge)

    resp = Response(status_code=302)
    # Store a short-lived session marker so the callback can verify ownership
    set_oauth_state_cookies(resp, state=sid, next_url="/", request=request, ttl=600, provider="spotify")
    resp.headers["Location"] = auth_url
    return resp


@router.get("/callback")
async def spotify_callback(request: Request) -> Response:
    """Handle Spotify OAuth callback.

    The callback validates session ownership, exchanges the code, and persists
    the tokens to the unified store using the authenticated user ID.
    """
    code = request.query_params.get("code")
    state = request.query_params.get("state")

    # Resolve session id from cookie or header
    sid = resolve_session_id(request=request)
    if not sid:
        raise HTTPException(status_code=400, detail="missing_session")

    # Get PKCE challenge bound to session
    pkce = get_pkce_challenge(sid)
    if not pkce:
        raise HTTPException(status_code=400, detail="invalid_session")

    # Verify state
    if state != pkce.state:
        clear_pkce_challenge(sid)
        raise HTTPException(status_code=400, detail="state_mismatch")

    if not code:
        clear_pkce_challenge(sid)
        raise HTTPException(status_code=400, detail="missing_code")

    try:
        token_data = await exchange_code(code=code, code_verifier=pkce.verifier)

        # Persist tokens. Prefer authenticated user; otherwise attach to session id.
        user_id = get_current_user_id(request=request)
        if not user_id or user_id == "anon":
            # No authenticated user: bind tokens to session id as user placeholder
            user_id = sid

        now = int(time.time())
        token = ThirdPartyToken(
            user_id=user_id,
            provider="spotify",
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            scope=token_data.get("scope"),
            expires_at=int(token_data.get("expires_at", now + int(token_data.get("expires_in", 3600)))),
            created_at=now,
            updated_at=now,
        )

        await upsert_token(token)

    except Exception as e:
        logger.error(f"Spotify token exchange failed: {e}")
        raise HTTPException(status_code=502, detail="token_exchange_failed")
    finally:
        clear_pkce_challenge(sid)

    resp = Response(status_code=302)
    app_url = os.getenv("APP_URL", "http://localhost:3000")
    resp.headers["Location"] = app_url
    clear_oauth_state_cookies(resp, request, provider="spotify")
    return resp


@router.delete("/disconnect")
async def spotify_disconnect(request: Request) -> dict:
    """Disconnect Spotify by marking tokens as invalid."""
    # TODO: Get from authenticated user
    user_id = "default"

    client = SpotifyClient(user_id)
    success = await client.disconnect()

    return {"ok": success}


@router.get("/status")
async def spotify_status(request: Request) -> dict:
    """Get Spotify connection status."""
    # TODO: Get from authenticated user
    user_id = "default"

    client = SpotifyClient(user_id)
    tokens = await client._get_tokens()

    if not tokens:
        return {"connected": False}

    return {
        "connected": True,
        "expires_at": tokens.expires_at,
        "scope": tokens.scope,
        "time_until_expiry": tokens.time_until_expiry()
    }
