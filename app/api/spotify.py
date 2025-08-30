from __future__ import annotations

import os
import secrets
import logging
import time

from fastapi import APIRouter, Request, Response, HTTPException, Depends

from ..cookies import set_oauth_state_cookies, clear_oauth_state_cookies, set_named_cookie, clear_named_cookie
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
from ..security import jwt_decode
from ..api.auth import _jwt_secret


# Test compatibility: add _jwt_decode function that tests expect
def _jwt_decode(token: str, secret: str, algorithms=None) -> dict:
    """Decode JWT token for test compatibility."""
    return jwt_decode(token, secret, algorithms=algorithms or ["HS256"])
from ..metrics import OAUTH_START, OAUTH_CALLBACK, OAUTH_IDEMPOTENT

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/spotify")

SPOTIFY_AUTH = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"


def _pkce_challenge() -> SpotifyPKCE:
    """Generate PKCE challenge for OAuth flow."""
    oauth = SpotifyOAuth()
    return oauth.generate_pkce()


if os.getenv("SPOTIFY_LOGIN_LEGACY", "0") == "1":
    @router.get("/login")
    async def spotify_login(request: Request, user_id: str = Depends(get_current_user_id)) -> Response:
        """Legacy Spotify login endpoint (enabled only when SPOTIFY_LOGIN_LEGACY=1).

        This route is intentionally excluded from import/mount when the
        feature flag is not set to reduce attack surface. The implementation
        is deprecated and kept behind the explicit opt-in.
        """
        logger.info("🎵 SPOTIFY LOGIN: Starting Spotify OAuth flow", extra={
            "meta": {
                "user_id": user_id,
                "client_ip": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("User-Agent", "unknown"),
                "has_cookies": len(request.cookies) > 0,
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
            }
        })

        # Store verifier tied to the session (session id from cookie or resolved)
        sid = resolve_session_id(request=request)
        logger.info("🎵 SPOTIFY LOGIN: Storing PKCE challenge", extra={
            "meta": {
                "session_id": sid,
                "session_id_length": len(sid) if sid else 0,
            }
        })

        pkce_data = SpotifyPKCE(verifier=verifier, challenge=challenge, state=state, created_at=time.time())
        store_pkce_challenge(sid, pkce_data)

        logger.info("🎵 SPOTIFY LOGIN: Building authorization URL...")
        auth_url = make_authorize_url.build(state=state, code_challenge=challenge)
        logger.info("🎵 SPOTIFY LOGIN: Authorization URL built", extra={"meta": {"auth_url_length": len(auth_url)}})

        # Return JSON response with the auth URL
        from fastapi.responses import JSONResponse

        response = JSONResponse(content={"ok": True, "authorize_url": auth_url, "session_id": sid})

        # NOTE: legacy route sets a temporary cookie from bearer/header; retain behavior
        # only when explicitly enabled via the SPOTIFY_LOGIN_LEGACY flag.
        # Use canonical access cookie name `GSNH_AT` only; do not consult legacy
        # `auth_token` cookie to reduce confusion and surface area.
        from ..cookie_names import GSNH_AT
        from ..cookies import read_access_cookie

        jwt_token = read_access_cookie(request)

        if jwt_token:
            # Temp cookie for legacy flow: HttpOnly + SameSite=Lax; Secure per env
            set_named_cookie(
                response,
                name="spotify_oauth_jwt",
                value=jwt_token,
                ttl=600,
                request=request,
                httponly=True,
                path="/",
                samesite="lax",
            )
            logger.info("🎵 SPOTIFY LOGIN: Set spotify_oauth_jwt cookie", extra={"meta": {"token_length": len(jwt_token)}})

        logger.info("🎵 SPOTIFY LOGIN: Returning response", extra={"meta": {"has_authorize_url": bool(auth_url), "authorize_url_length": len(auth_url)}})
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
            "has_gsnh_at": bool(request.cookies.get(GSNH_AT)),
            "authorization_header": bool(request.headers.get("Authorization")),
            "host": request.headers.get("host"),
            "origin": request.headers.get("origin")
        }
    })
    import uuid

    # Basic CSRF hardening: validate Origin/Referer against allowed origins
    try:
        allowed = [o.strip() for o in (os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000") or "").split(",") if o.strip()]
        # Always allow same-origin calls to backend (when called directly)
        try:
            backend_origin = f"{request.url.scheme}://{request.headers.get('host','').split(',')[0]}".lower()
            if backend_origin and backend_origin not in allowed:
                allowed.append(backend_origin)
        except Exception:
            pass
        origin = (request.headers.get("origin") or "").strip().lower()
        referer = (request.headers.get("referer") or "").strip().lower()
        ref_origin = ""
        if referer:
            try:
                from urllib.parse import urlparse

                p = urlparse(referer)
                if p.scheme and p.netloc:
                    ref_origin = f"{p.scheme}://{p.netloc}".lower()
            except Exception:
                ref_origin = ""
        if origin and origin not in allowed and ref_origin and ref_origin not in allowed:
            raise HTTPException(status_code=403, detail="origin_not_allowed")
    except HTTPException:
        raise
    except Exception:
        # Best-effort; do not block if parsing fails
        pass

    # Per-user rate limiting to avoid TX spam
    try:
        from ..token_store import incr_login_counter

        minute = await incr_login_counter(f"rl:spotify_connect:user:{user_id}:m", 60)
        hour = await incr_login_counter(f"rl:spotify_connect:user:{user_id}:h", 3600)
        if minute > 10 or hour > 100:
            raise HTTPException(status_code=429, detail="too_many_requests")
    except HTTPException:
        raise
    except Exception:
        pass
    import jwt
    import time
    from ..api.auth import _jwt_secret

    # user_id is provided by dependency injection (requires authentication)
    if not user_id or user_id == "anon":
        logger.error("Spotify connect: unauthenticated request")
        from ..http_errors import unauthorized

        raise unauthorized(code="authentication_failed", message="authentication failed", hint="reconnect Spotify account")
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
            "verifier_length": len(verifier)
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
        "exp": int(time.time()) + 600,  # 10 minutes
        "iat": int(time.time()),
    }

    secret = _jwt_secret()
    # Include issuer/audience when configured to harden state JWTs
    iss = os.getenv("JWT_ISS") or os.getenv("JWT_ISSUER")
    aud = os.getenv("JWT_AUD") or os.getenv("JWT_AUDIENCE")
    if iss:
        state_payload["iss"] = iss
    if aud:
        state_payload["aud"] = aud

    # Include kid header when key pool configured to allow rotation in future
    try:
        from ..api.auth import _primary_kid_secret  # type: ignore

        try:
            kid, _ = _primary_kid_secret()
        except Exception:
            kid = None
    except Exception:
        kid = None
    headers = {"kid": kid} if kid else None

    # Encode state JWT (no logging of token contents anywhere)
    state = jwt.encode(state_payload, secret, algorithm="HS256", headers=headers)

    logger.info("🎵 SPOTIFY CONNECT: JWT state created", extra={
        "meta": {
            "state_length": len(state),
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

    # Never log the URL itself; log only metadata
    logger.info("🎵 SPOTIFY CONNECT: Authorization URL built", extra={
        "meta": {
            "auth_url_length": len(auth_url)
        }
    })

    # If in test mode, short-circuit to backend callback for deterministic e2e tests
    if os.getenv("SPOTIFY_TEST_MODE", "0") == "1":
        backend = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        original_url = auth_url
        auth_url = f"{backend}/v1/spotify/callback?code=fake&state={state}"

        logger.info("🎵 SPOTIFY CONNECT: TEST MODE - Using short-circuit URL", extra={
            "meta": {
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


@router.get("/health")
async def spotify_health(request: Request):
    """Lightweight health check to confirm router mount and env wiring.

    Returns basic config flags without exposing secrets.
    """
    from fastapi.responses import JSONResponse
    try:
        client_id_set = bool(os.getenv("SPOTIFY_CLIENT_ID"))
        redirect_set = bool(os.getenv("SPOTIFY_REDIRECT_URI"))
        test_mode = os.getenv("SPOTIFY_TEST_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}
        return JSONResponse({
            "ok": True,
            "client_id_set": client_id_set,
            "redirect_set": redirect_set,
            "test_mode": test_mode,
        }, status_code=200)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


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
    # Pre-decode diagnostics for `state` integrity without leaking secrets
    try:
        raw = state or ""
        state_diag = {
            "state_len": len(raw),
            "dot_count": raw.count("."),
            "looks_like_jwt": raw.count(".") == 2,
        }
        # Environment parity hints (do not log secret values)
        try:
            iss = (os.getenv("JWT_ISS") or os.getenv("JWT_ISSUER") or "").strip()
            aud = (os.getenv("JWT_AUD") or os.getenv("JWT_AUDIENCE") or "").strip()
            try:
                sec = _jwt_secret()
                sec_len = len(sec or "")
            except Exception:
                sec_len = 0
            state_diag.update({
                "jwt_iss_set": bool(iss),
                "jwt_aud_set": bool(aud),
                "jwt_secret_len": sec_len,
            })
        except Exception:
            pass
        logger.info("🎵 SPOTIFY CALLBACK: state diagnostics", extra={"meta": state_diag})
    except Exception:
        pass
    # Compatibility log markers expected by tests
    logger.info("spotify.callback:start")

    # 1) Verify state JWT (no cookies needed)
    logger.info("🎵 SPOTIFY CALLBACK: Step 1 - Verifying JWT state...")
    if not state:
        logger.error("🎵 SPOTIFY CALLBACK: Missing state param")
        # Return 400 for API calls, redirect for browser-like requests
        accept = request.headers.get("Accept", "")
        user_agent = request.headers.get("User-Agent", "")
        # API clients or programmatic requests get 400, browsers get redirect
        if accept.startswith("application/json") or not user_agent or "testclient" in user_agent.lower():
            raise HTTPException(status_code=400, detail="missing_state")
        from starlette.responses import RedirectResponse
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=bad_state", status_code=302)
    if not code:
        logger.error("🎵 SPOTIFY CALLBACK: Missing authorization code")
        # Return 400 for API calls, redirect for browser-like requests
        accept = request.headers.get("Accept", "")
        user_agent = request.headers.get("User-Agent", "")
        # API clients or programmatic requests get 400, browsers get redirect
        if accept.startswith("application/json") or not user_agent or "testclient" in user_agent.lower():
            raise HTTPException(status_code=400, detail="missing_code")
        from starlette.responses import RedirectResponse
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=missing_code", status_code=302)
    try:
        secret = _jwt_secret()
        # Use centralized decode function to honour issuer/audience/leeway and
        # allow tests to monkeypatch _jwt_decode. Pass only the standard args so
        # test monkeypatches with older signatures continue to work.
        payload = jwt_decode(state, secret, algorithms=["HS256"])
        # Support multiple JWT payload shapes for compatibility with tests and
        # older callers: prefer explicit tx/uid, then fall back to sid/sub.
        tx_id = payload.get("tx") or payload.get("sid") or payload.get("t")
        uid = payload.get("uid") or payload.get("sub") or payload.get("user")
        exp_time = payload.get("exp", 0)

        logger.debug("🎵 SPOTIFY CALLBACK: JWT decoded tx=%s uid=%s", tx_id, uid)
        # Compatibility marker for tests that assert logging order
        logger.info("spotify.callback:jwt_ok")
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

    # 2) Recover PKCE + user from server store. We prefer the stateless tx_id
    # flow, but fall back to session-based PKCE storage when tx is not present
    # (compatibility with legacy/session flows and tests that monkeypatch
    # `get_pkce_challenge_by_state`).
    logger.info("🎵 SPOTIFY CALLBACK: Step 2 - Recovering transaction from store...")
    tx = None
    if tx_id:
        tx = pop_tx(tx_id)  # atomically fetch & delete

    # Fallback: look up PKCE by session id + state (legacy flow). If used, ensure
    # we clear the PKCE entry to prevent replay.
    if not tx:
        session_id = payload.get("sid") or payload.get("session")
        if session_id and state:
            pkce = get_pkce_challenge_by_state(session_id, state)
            if pkce:
                tx = {
                    "user_id": uid,
                    "code_verifier": pkce.verifier,
                    "ts": getattr(pkce, "created_at", int(time.time()))
                }
                try:
                    clear_pkce_challenge_by_state(session_id, state)
                except Exception:
                    pass

    if not tx:
        logger.error("🎵 SPOTIFY CALLBACK: No transaction found in store", extra={
                "meta": {
                "tx_id": tx_id,
                "session_id": payload.get("sid"),
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
                "session_id": payload.get("sid"),
                "expected_user": uid,
                "stored_user": tx.get("user_id"),
                "user_mismatch": True
            }
        })
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=user_mismatch", status_code=302)

    # The code_verifier is sensitive; never log or include previews. Only use it
    # for the token exchange and keep it out of logs and responses.
    code_verifier = tx["code_verifier"]
    tx_timestamp = tx.get("ts", 0)

    logger.info("🎵 SPOTIFY CALLBACK: transaction recovered tx=%s uid=%s", tx_id, uid)

    # 3) Exchange code → tokens
    logger.info("🎵 SPOTIFY CALLBACK: Step 3 - Exchanging authorization code for tokens...")
    try:
        logger.debug("🎵 SPOTIFY CALLBACK: calling token endpoint tx=%s", tx_id)

        token_data = await exchange_code(code=code, code_verifier=code_verifier)

        # exchange_code may return a dict in tests/mocks or a ThirdPartyToken
        # dataclass in production. Normalize to ThirdPartyToken for downstream
        # processing.
        if isinstance(token_data, dict):
            now = int(time.time())
            expires_at = int(token_data.get("expires_at", now + int(token_data.get("expires_in", 3600))))
            token_data = ThirdPartyToken(
                id=f"spotify:{secrets.token_hex(8)}",
                user_id=uid,
                provider="spotify",
                access_token=token_data.get("access_token", ""),
                refresh_token=token_data.get("refresh_token"),
                scope=token_data.get("scope"),
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )

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

        persisted = await upsert_token(token_for_storage)

        logger.info(
            "🎵 SPOTIFY CALLBACK: tokens persisted",
            extra={"meta": {"tx_id": tx_id, "user_id": uid, "persisted": bool(persisted)}},
        )
        # Compatibility marker for tests that assert logging order
        logger.info("spotify.callback:tokens_persisted")

        # Metrics: oauth callback success
        try:
            OAUTH_CALLBACK.labels("spotify").inc()
        except Exception as e:
            logger.debug("🎵 SPOTIFY CALLBACK: metrics increment failed: %s", str(e))

    except Exception as e:
        # Guard against token_data being None or undefined when logging
        has_at = False
        has_rt = False
        try:
            if 'token_data' in locals() and token_data is not None:
                has_at = bool(getattr(token_data, 'access_token', None))
                has_rt = bool(getattr(token_data, 'refresh_token', None))
        except Exception:
            has_at = False
            has_rt = False
        logger.error(
            "🎵 SPOTIFY CALLBACK: Token persistence failed",
            extra={
                "meta": {
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "user_id": uid,
                    "tx_id": tx_id,
                    "has_access_token": has_at,
                    "has_refresh_token": has_rt,
                }
            },
        )
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=token_save_failed", status_code=302)

    # 5) Redirect to UI success
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    # Redirect to UI; use query parameter format for compatibility with tests
    redirect_url = f"{frontend_url}/settings?spotify=connected"

    logger.info("🎵 SPOTIFY CALLBACK: completed tx=%s uid=%s", tx_id, uid)

    return RedirectResponse(redirect_url, status_code=302)


@router.delete("/disconnect")
async def spotify_disconnect(request: Request) -> dict:
    """Disconnect Spotify by marking tokens as invalid."""
    # Require authenticated user
    try:
        # Internal call — use helper to resolve user_id without FastAPI Depends
        from ..deps.user import resolve_user_id

        user_id = resolve_user_id(request=request)
        if user_id == "anon":
            raise Exception("unauthenticated")
    except Exception:
        from ..http_errors import unauthorized

        raise unauthorized(message="authentication required", hint="login or include Authorization header")

    # Mark tokens invalid and record revocation timestamp using async DAO
    success = await SpotifyClient(user_id).disconnect()
    if success:
        try:
            # Use centralized async token store to avoid blocking the event loop
            from ..auth_store_tokens import mark_invalid as mark_token_invalid

            await mark_token_invalid(user_id, "spotify")
        except Exception as e:
            logger.warning("🎵 SPOTIFY DISCONNECT: failed to mark token invalid via DAO", extra={"meta": {"error": str(e)}})

    return {"ok": success}


@router.get("/status")
async def spotify_status(request: Request) -> dict:
    """Get Spotify integration status.

    Returns a richer shape to avoid dead route usage on the frontend:
    { connected: bool, devices_ok: bool, state_ok: bool, reason?: string }
    """
    from fastapi.responses import JSONResponse

    # Check if user is authenticated
    current_user = None
    try:
        current_user = get_current_user_id(request=request)
    except Exception:
        pass

    if not current_user or current_user == "anon":
        # Return status for unauthenticated users - not connected
        body: dict = {"connected": False, "devices_ok": False, "state_ok": False, "reason": "not_authenticated"}
        return JSONResponse(body, status_code=200)

    client = SpotifyClient(current_user)

    # First determine token connectivity without hitting Spotify
    connected = False
    reason: str | None = None
    try:
        token = await client._bearer_token_only()
        connected = bool(token)
    except RuntimeError as e:
        connected = False
        reason = str(e)

    # Probe devices and playback state best-effort; do not raise
    devices_ok = False
    state_ok = False
    if connected:
        try:
            devices = await client.get_devices()
            # If the API call succeeded, consider devices_ok True even if empty
            devices_ok = True
        except Exception as e:
            try:
                logger.warning("🎵 SPOTIFY STATUS: devices probe failed", extra={"meta": {"error": str(e)}})
            except Exception:
                pass
        try:
            # current playback probe; success means token is valid and API reachable
            _ = await client.get_currently_playing()
            state_ok = True
        except Exception as e:
            try:
                logger.warning("🎵 SPOTIFY STATUS: state probe failed", extra={"meta": {"error": str(e)}})
            except Exception:
                pass

    body: dict = {"connected": connected, "devices_ok": devices_ok, "state_ok": state_ok}
    if not connected and reason:
        body["reason"] = reason
    return JSONResponse(body, status_code=200)
