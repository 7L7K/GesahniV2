from __future__ import annotations

import os
import secrets
import logging
import time
from urllib.parse import urlencode, unquote

import aiohttp
from fastapi import APIRouter, Request, Response, HTTPException

from ..cookies import set_oauth_state_cookies, clear_oauth_state_cookies, set_named_cookie, clear_named_cookie, set_auth_cookies
from ..cookie_config import get_cookie_config
from .oauth_store import put_tx, pop_tx
from ..integrations.spotify.oauth import (
    store_pkce_challenge,
    get_pkce_challenge,
    get_pkce_challenge_by_state,
    clear_pkce_challenge,
    clear_pkce_challenge_by_state,
    SpotifyPKCE,
    SpotifyOAuth,
    make_authorize_url,
    exchange_code,
    STATE_KEY,
    PKCE_VERIFIER_KEY,
)
from ..integrations.spotify.client import SpotifyClient
from ..auth_store_tokens import upsert_token
from ..cookie_names import GSNH_AT
from ..tokens import make_access, make_refresh, get_default_access_ttl, get_default_refresh_ttl
from ..models.third_party_tokens import ThirdPartyToken
from ..deps.user import get_current_user_id, resolve_session_id
from ..security import _jwt_decode
from ..api.auth import _jwt_secret
from ..metrics import OAUTH_START, OAUTH_CALLBACK, OAUTH_IDEMPOTENT

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/spotify")

SPOTIFY_AUTH = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"


def _pkce_challenge() -> SpotifyPKCE:
    """Generate PKCE challenge for OAuth flow."""
    oauth = SpotifyOAuth()
    return oauth.generate_pkce()


@router.get("/login")
async def spotify_login(request: Request, user_id: str = get_current_user_id) -> Response:
    """Deprecated: legacy Spotify login. Use /connect from authenticated settings instead.

    Hidden behind feature flag SPOTIFY_LOGIN_LEGACY=1.
    """
    if os.getenv("SPOTIFY_LOGIN_LEGACY", "0") != "1":
        raise HTTPException(status_code=404, detail="not_found")
    logger.info("🎵 SPOTIFY LOGIN: Starting Spotify OAuth flow", extra={
        "meta": {
            "user_id": user_id,
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("User-Agent", "unknown"),
            "has_cookies": len(request.cookies) > 0,
            "cookie_names": list(request.cookies.keys()) if request.cookies else []
        }
    })

    # Generate PKCE and authorization URL via helper
    logger.info("🎵 SPOTIFY LOGIN: Generating PKCE challenge...")
    state, challenge, verifier = await make_authorize_url.prepare_pkce()
    logger.info("🎵 SPOTIFY LOGIN: PKCE generated", extra={
        "meta": {
            "state_length": len(state),
            "challenge_length": len(challenge),
            "verifier_length": len(verifier),
            "state_prefix": state[:10] + "...",
            "challenge_prefix": challenge[:10] + "..."
        }
    })

    # Store verifier tied to the session (session id from cookie or resolved)
    sid = resolve_session_id(request=request)
    logger.info("🎵 SPOTIFY LOGIN: Storing PKCE challenge", extra={
        "meta": {
            "session_id": sid,
            "session_id_length": len(sid) if sid else 0
        }
    })

    pkce_data = SpotifyPKCE(verifier=verifier, challenge=challenge, state=state, created_at=time.time())
    store_pkce_challenge(sid, pkce_data)

    logger.info("🎵 SPOTIFY LOGIN: Building authorization URL...")
    auth_url = make_authorize_url.build(state=state, code_challenge=challenge)
    logger.info("🎵 SPOTIFY LOGIN: Authorization URL built", extra={
        "meta": {
            "auth_url_length": len(auth_url),
            "auth_url_prefix": auth_url[:100] + "..." if len(auth_url) > 100 else auth_url
        }
    })

    # Return JSON response with the auth URL
    from fastapi.responses import JSONResponse
    response = JSONResponse(content={
        "ok": True,
        "authorize_url": auth_url,
        "session_id": sid
    })

    # Set a cookie with the JWT token for the callback
    # Extract JWT from Authorization header or main auth cookie
    auth_header = request.headers.get("Authorization", "")
    jwt_token = None

    if auth_header.startswith("Bearer "):
        jwt_token = auth_header[7:]  # Remove "Bearer " prefix
    else:
        # Try to get JWT from main auth cookie
        jwt_token = request.cookies.get("auth_token")

    if jwt_token:
        # Set temporary spotify_oauth_jwt cookie (callback-scoped)
        set_named_cookie(
            response,
            name="spotify_oauth_jwt",
            value=jwt_token,
            ttl=600,
            request=request,
            httponly=True,
            path="/",
        )
        logger.info("🎵 SPOTIFY LOGIN: Set spotify_oauth_jwt cookie", extra={"meta": {"token_length": len(jwt_token)}})

    logger.info("🎵 SPOTIFY LOGIN: Returning response", extra={
        "meta": {
            "response_keys": list(response.__dict__.keys()),
            "has_authorize_url": bool(auth_url),
            "authorize_url_length": len(auth_url)
        }
    })

    return response


@router.get("/debug")
async def spotify_debug(request: Request):
    """Debug endpoint to test authentication."""
    try:
        user_id = get_current_user_id(request)
        return {"status": "ok", "user_id": user_id, "authenticated": True}
    except Exception as e:
        logger.error(f"Debug auth error: {e}")
        return {"status": "error", "error": str(e), "authenticated": False}

from fastapi import Depends


@router.get("/connect")
async def spotify_connect(request: Request, user_id: str = Depends(get_current_user_id)) -> Response:
    """Initiate Spotify OAuth flow with stateless PKCE.

    This route creates a JWT state containing user_id + tx_id, and stores
    the PKCE code_verifier server-side keyed by tx_id. No cookies required.

    Returns the authorization URL as JSON for frontend consumption.
    """
    # Enhanced logging for debugging
    logger.info("🎵 SPOTIFY CONNECT: Request started", extra={
        "meta": {
            "user_id": user_id,
            "cookies_count": len(request.cookies),
            "cookie_names": list(request.cookies.keys()),
            "has_gsnh_at": bool(request.cookies.get(GSNH_AT)),
            "has_auth_token": bool(request.cookies.get("auth_token")),
            "authorization_header": bool(request.headers.get("Authorization")),
            "host": request.headers.get("host"),
            "origin": request.headers.get("origin"),
            "user_agent": request.headers.get("user-agent", "")[:50] + "..." if len(request.headers.get("user-agent", "")) > 50 else request.headers.get("user-agent", "")
        }
    })
    import uuid
    import jwt
    import time
    from ..api.auth import _jwt_secret

    # user_id is provided by dependency injection (requires authentication)
    if not user_id or user_id == "anon":
        logger.error("Spotify connect: unauthenticated request")
        raise HTTPException(status_code=401, detail="authentication_failed")
    logger.info(f"Spotify connect: authenticated user_id='{user_id}'")

    logger.info("🎵 SPOTIFY CONNECT: Preparing stateless OAuth flow", extra={
        "meta": {
            "user_id": user_id,
            "component": "spotify_connect"
        }
    })

    # Generate PKCE challenge
    logger.info("🎵 SPOTIFY CONNECT: Generating PKCE challenge...")
    state_raw, challenge, verifier = await make_authorize_url.prepare_pkce()
    tx_id = uuid.uuid4().hex

    logger.info("🎵 SPOTIFY CONNECT: PKCE challenge generated", extra={
        "meta": {
            "tx_id": tx_id,
            "challenge_length": len(challenge),
            "verifier_length": len(verifier),
            "challenge_preview": challenge[:20] + "...",
            "verifier_preview": verifier[:20] + "..."
        }
    })

    # Persist PKCE + user for 10 minutes
    tx_data = {
        "user_id": user_id,
        "code_verifier": verifier,
        "ts": int(time.time())
    }

    logger.info("🎵 SPOTIFY CONNECT: Storing transaction data", extra={
        "meta": {
            "tx_id": tx_id,
            "user_id": user_id,
            "tx_data_keys": list(tx_data.keys()),
            "ttl_seconds": 600
        }
    })

    put_tx(tx_id, tx_data, ttl_seconds=600)

    # Create JWT state with user_id + tx_id
    logger.info("🎵 SPOTIFY CONNECT: Creating JWT state...")
    state_payload = {
        "tx": tx_id,
        "uid": user_id,
        "exp": int(time.time()) + 600  # 10 minutes
    }

    secret = _jwt_secret()
    state = jwt.encode(state_payload, secret, algorithm="HS256")

    logger.info("🎵 SPOTIFY CONNECT: JWT state created", extra={
        "meta": {
            "state_length": len(state),
            "state_preview": state[:50] + "...",
            "payload_tx": tx_id,
            "payload_uid": user_id,
            "payload_exp": state_payload["exp"],
            "expires_in_minutes": 10
        }
    })

    # Metrics: oauth start
    try:
        OAUTH_START.labels("spotify").inc()
    except Exception:
        pass

    logger.info("🎵 SPOTIFY CONNECT: Stateless OAuth tx saved", extra={
        "meta": {
            "tx_id": tx_id,
            "user_id": user_id,
            "state_jwt_length": len(state)
        }
    })

    logger.info("🎵 SPOTIFY CONNECT: Building authorization URL...")
    auth_url = make_authorize_url.build(state=state, code_challenge=challenge)

    logger.info("🎵 SPOTIFY CONNECT: Authorization URL built", extra={
        "meta": {
            "auth_url_length": len(auth_url),
            "auth_url_preview": auth_url[:100] + "...",
            "state_in_url": state in auth_url,
            "challenge_in_url": challenge in auth_url
        }
    })

    # If in test mode, short-circuit to backend callback for deterministic e2e tests
    if os.getenv("SPOTIFY_TEST_MODE", "0") == "1":
        backend = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        original_url = auth_url
        auth_url = f"{backend}/v1/spotify/callback?code=fake&state={state}"

        logger.info("🎵 SPOTIFY CONNECT: TEST MODE - Using short-circuit URL", extra={
            "meta": {
                "original_url": original_url[:100] + "...",
                "test_url": auth_url,
                "backend": backend
            }
        })

    # Return JSON response with the auth URL
    from fastapi.responses import JSONResponse
    response = JSONResponse(content={
        "ok": True,
        "authorize_url": auth_url,
    })

    logger.info("🎵 SPOTIFY CONNECT: Stateless flow complete", extra={
        "meta": {
            "response_content": response.body.decode() if hasattr(response, 'body') else "JSONResponse",
            "no_cookies_set": True,
            "stateless_flow": True,
            "tx_id": tx_id,
            "user_id": user_id
        }
    })

    return response


@router.get("/callback-test")
async def spotify_callback_test(request: Request):
    """Simple test callback."""
    from fastapi.responses import JSONResponse
    return JSONResponse(content={
        "status": "ok",
        "message": "Test callback works",
        "params": dict(request.query_params),
        "cookies": list(request.cookies.keys())
    })


@router.get("/debug-cookie")
async def spotify_debug_cookie(request: Request) -> dict:
    """Dev-only helper (stubbed in production)."""
    if os.getenv("DEV_MODE") or os.getenv("SPOTIFY_TEST_MODE") == "1":
        return {"cookies": list(request.cookies.keys())}
    raise HTTPException(status_code=404, detail="not_found")

@router.get("/callback")
async def spotify_callback(request: Request, code: str | None = None, state: str | None = None) -> Response:
    """Handle Spotify OAuth callback with stateless JWT state.

    Recovers user_id + PKCE code_verifier from JWT state + server store.
    No cookies required - works even if browser sends zero cookies.
    """
    import jwt
    from starlette.responses import RedirectResponse
    from ..api.auth import _jwt_secret

    logger.info("🎵 SPOTIFY CALLBACK: start has_code=%s has_state=%s", bool(code), bool(state))

    # 1) Verify state JWT (no cookies needed)
    logger.info("🎵 SPOTIFY CALLBACK: Step 1 - Verifying JWT state...")
    try:
        secret = _jwt_secret()
        payload = jwt.decode(state, secret, algorithms=["HS256"])
        tx_id = payload["tx"]
        uid = payload["uid"]
        exp_time = payload.get("exp", 0)

        logger.debug("🎵 SPOTIFY CALLBACK: JWT decoded tx=%s uid=%s", tx_id, uid)
    except jwt.ExpiredSignatureError as e:
        logger.error("🎵 SPOTIFY CALLBACK: JWT state expired", extra={
            "meta": {"error_type": "ExpiredSignatureError", "error_message": str(e)}
        })
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=expired_state", status_code=302)
    except jwt.InvalidTokenError as e:
        logger.error("🎵 SPOTIFY CALLBACK: Invalid JWT state", extra={
            "meta": {"error_type": "InvalidTokenError", "error_message": str(e)}
        })
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=bad_state", status_code=302)
    except Exception as e:
        logger.error("🎵 SPOTIFY CALLBACK: JWT decode error", extra={
            "meta": {"error_type": type(e).__name__, "error_message": str(e)}
        })
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=bad_state", status_code=302)

    # 2) Recover PKCE + user from server store
    logger.info("🎵 SPOTIFY CALLBACK: Step 2 - Recovering transaction from store...")
    tx = pop_tx(tx_id)  # atomically fetch & delete

    if not tx:
        logger.error("🎵 SPOTIFY CALLBACK: No transaction found in store", extra={
                "meta": {
                "tx_id": tx_id,
                "user_id": uid,
                "store_empty": True
            }
        })
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=expired_txn", status_code=302)

    if tx.get("user_id") != uid:
        logger.error("🎵 SPOTIFY CALLBACK: User ID mismatch in transaction", extra={
            "meta": {
                "tx_id": tx_id,
                "expected_user": uid,
                "stored_user": tx.get("user_id"),
                "user_mismatch": True
            }
        })
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=user_mismatch", status_code=302)

    code_verifier = tx["code_verifier"]
    tx_timestamp = tx.get("ts", 0)

    logger.info("🎵 SPOTIFY CALLBACK: transaction recovered tx=%s uid=%s", tx_id, uid)

    # 3) Exchange code → tokens
    logger.info("🎵 SPOTIFY CALLBACK: Step 3 - Exchanging authorization code for tokens...")
    try:
        logger.debug("🎵 SPOTIFY CALLBACK: calling token endpoint tx=%s", tx_id)

        token_data = await exchange_code(code=code, code_verifier=code_verifier)

        logger.info("🎵 SPOTIFY CALLBACK: token exchange successful tx=%s", tx_id)
    except Exception as e:
        logger.error("🎵 SPOTIFY CALLBACK: Token exchange failed", extra={
            "meta": {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "user_id": uid,
                "tx_id": tx_id,
                "code_provided": bool(code),
                "code_verifier_provided": bool(code_verifier),
                "token_data_type": type(token_data).__name__ if 'token_data' in locals() else 'undefined',
                "token_data_attributes": list(vars(token_data).keys()) if 'token_data' in locals() and hasattr(token_data, '__dict__') else 'N/A'
            }
        })
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=token_exchange_failed", status_code=302)

    # 4) Persist tokens for user
    logger.info("🎵 SPOTIFY CALLBACK: Step 4 - Persisting tokens to database...")
    try:
        # Access ThirdPartyToken attributes correctly (not dict-style)
        access_token = token_data.access_token
        refresh_token = token_data.refresh_token
        expires_at = token_data.expires_at

        logger.debug("🎵 SPOTIFY CALLBACK: persisting tokens tx=%s uid=%s", tx_id, uid)

        # Create a new ThirdPartyToken with the correct user_id
        token_for_storage = ThirdPartyToken(
            user_id=uid,
            provider="spotify",
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=token_data.scope,
        )

        await upsert_token(token_for_storage)

        logger.info("🎵 SPOTIFY CALLBACK: tokens persisted tx=%s uid=%s", tx_id, uid)

        # Metrics: oauth callback success
        try:
            OAUTH_CALLBACK.labels("spotify").inc()
        except Exception as e:
            logger.debug("🎵 SPOTIFY CALLBACK: metrics increment failed: %s", str(e))

    except Exception as e:
        logger.error("🎵 SPOTIFY CALLBACK: Token persistence failed", extra={
            "meta": {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "user_id": uid,
                "tx_id": tx_id,
                "has_access_token": bool(token_data.access_token),
                "has_refresh_token": bool(token_data.refresh_token)
            }
        })
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=token_save_failed", status_code=302)

    # 5) Redirect to UI success
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    redirect_url = f"{frontend_url}/settings#spotify?connected=1"

    logger.info("🎵 SPOTIFY CALLBACK: completed tx=%s uid=%s", tx_id, uid)

    return RedirectResponse(redirect_url, status_code=302)


@router.delete("/disconnect")
async def spotify_disconnect(request: Request) -> dict:
    """Disconnect Spotify by marking tokens as invalid."""
    # Require authenticated user
    try:
        user_id = get_current_user_id(request=request)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Mark tokens invalid and record revocation timestamp
    success = await SpotifyClient(user_id).disconnect()
    if success:
        # Update DB to set updated_at and is_valid=0
        import sqlite3
        conn = sqlite3.connect(os.getenv("THIRD_PARTY_TOKENS_DB", "third_party_tokens.db"))
        try:
            cur = conn.cursor()
            now = int(time.time())
            cur.execute("UPDATE third_party_tokens SET is_valid = 0, updated_at = ?, last_refresh_at = ? WHERE user_id = ? AND provider = ?", (now, now, user_id, "spotify"))
            conn.commit()
        finally:
            conn.close()

    return {"ok": success}


@router.get("/status")
async def spotify_status(request: Request) -> dict:
    """Get Spotify connection status for the current user/session."""
    from fastapi.responses import JSONResponse

    # Check if user is authenticated
    current_user = None
    try:
        current_user = get_current_user_id(request=request)
    except Exception:
        pass

    if not current_user or current_user == "anon":
        return JSONResponse({"error_code": "auth_required"}, status_code=401)

    # User is authenticated, check if they have Spotify tokens
    client = SpotifyClient(current_user)
    try:
        # Attempt to obtain a bearer token without making an API call
        token = await client._bearer_token_only()
        # If we got here, we are connected
        return JSONResponse({"connected": True}, status_code=200)
    except RuntimeError as e:
        reason = str(e)
        return JSONResponse({"connected": False, "reason": reason}, status_code=200)
