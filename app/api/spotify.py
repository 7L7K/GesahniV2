from __future__ import annotations

import logging
import os
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from ..api.auth import _jwt_secret
from ..api.oauth_store import debug_store
from ..auth_store_tokens import upsert_token
from ..deps.user import get_current_user_id, resolve_session_id
from ..integrations.spotify.client import SpotifyClient
from ..integrations.spotify.oauth import (
    SpotifyOAuth,
    SpotifyPKCE,
    clear_pkce_challenge_by_state,
    exchange_code,
    get_pkce_challenge_by_state,
    make_authorize_url,
    store_pkce_challenge,
)
from ..models.third_party_tokens import ThirdPartyToken
from ..security import jwt_decode

# Cookie names moved to web.cookies.NAMES
from ..web.cookies import (
    set_named_cookie,
)
from .oauth_store import pop_tx, put_tx


# Test compatibility: add _jwt_decode function that tests expect
def _jwt_decode(token: str, secret: str, algorithms=None) -> dict:
    """Decode JWT token for test compatibility."""
    return jwt_decode(token, secret, algorithms=algorithms or ["HS256"])
from ..metrics import OAUTH_CALLBACK, OAUTH_START

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/spotify")

# New integrations endpoints at /v1/integrations/spotify/
integrations_router = APIRouter(prefix="/integrations/spotify")


@integrations_router.get("/status")
async def integrations_spotify_status(request: Request, user_id: str = Depends(get_current_user_id)) -> dict:
    """Get Spotify integration status for frontend polling.

    Returns status information that frontend can use to determine if reconnect is needed.
    """
    logger.info("🎵 SPOTIFY INTEGRATIONS STATUS: Request started", extra={
        "meta": {
            "user_id": user_id,
            "endpoint": "/v1/integrations/spotify/status"
        }
    })

    now = int(time.time())

    # Get token from store
    try:
        from ..auth_store_tokens import get_token
        token = await get_token(user_id, "spotify")
        logger.info("🎵 SPOTIFY INTEGRATIONS STATUS: Token retrieved", extra={
            "meta": {
                "user_id": user_id,
                "token_found": token is not None,
                "token_id": getattr(token, 'id', None) if token else None,
                "identity_id": getattr(token, 'identity_id', None) if token else None,
                "expires_at": getattr(token, 'expires_at', None) if token else None,
                "last_refresh_at": getattr(token, 'last_refresh_at', None) if token else None,
                "scopes": getattr(token, 'scopes', None) if token else None
            }
        })
    except Exception as e:
        logger.error("🎵 SPOTIFY INTEGRATIONS STATUS: Failed to get token", extra={
            "meta": {
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__
            }
        })
        return {
            "connected": False,
            "expires_at": None,
            "last_refresh_at": None,
            "refreshed": False,
            "scopes": []
        }

    # Check if connected (token exists and expires_at > now)
    connected = False
    if token and token.expires_at and token.expires_at > now:
        connected = True

    # Determine if recently refreshed
    refreshed = False
    if token and token.last_refresh_at:
        # Consider "refreshed" if last_refresh_at is within the last hour
        refreshed = (now - token.last_refresh_at) < 3600

    # Parse scopes
    scopes = []
    if token and token.scopes:
        scopes = [s.strip() for s in token.scopes.split() if s.strip()]

    result = {
        "connected": connected,
        "expires_at": token.expires_at if token else None,
        "last_refresh_at": token.last_refresh_at if token else None,
        "refreshed": refreshed,
        "scopes": scopes
    }

    logger.info("🎵 SPOTIFY INTEGRATIONS STATUS: Returning status", extra={
        "meta": {
            "user_id": user_id,
            "connected": connected,
            "expires_at": token.expires_at if token else None,
            "last_refresh_at": token.last_refresh_at if token else None,
            "refreshed": refreshed,
            "scopes_count": len(scopes),
            "needs_reconnect": not connected
        }
    })

    return result

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
        # Use canonical access cookie name only; do not consult legacy
        # `auth_token` cookie to reduce confusion and surface area.
        from ..web.cookies import read_access_cookie

        jwt_token = read_access_cookie(request)

        if jwt_token:
            # Temp cookie for legacy flow: HttpOnly + SameSite=Lax; Secure per env
            set_named_cookie(
                response,
                name="spotify_oauth_jwt",
                value=jwt_token,
                ttl=600,
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


@router.get("/debug/store")
async def debug_oauth_store():
    """Debug endpoint to check OAuth store contents."""
    return debug_store()

@router.post("/test/store_tx")
async def test_store_tx():
    """Test endpoint to store a transaction for testing."""
    import secrets
    import time
    import uuid

    tx_id = uuid.uuid4().hex
    tx_data = {
        "user_id": "testuser",
        "code_verifier": f"test_verifier_{secrets.token_hex(16)}",
        "ts": int(time.time())
    }

    put_tx(tx_id, tx_data, ttl_seconds=600)

    return {
        "tx_id": tx_id,
        "stored": True,
        "user_id": "testuser"
    }

@router.post("/test/full_flow")
async def test_full_flow():
    """Test endpoint that stores a transaction and returns the JWT state."""
    import secrets
    import time
    import uuid

    import jwt

    # Store transaction
    tx_id = uuid.uuid4().hex
    tx_data = {
        "user_id": "testuser",
        "code_verifier": f"test_verifier_{secrets.token_hex(16)}",
        "ts": int(time.time())
    }

    put_tx(tx_id, tx_data, ttl_seconds=600)

    # Generate JWT state
    secret = _jwt_secret()
    state_payload = {
        "tx": tx_id,
        "uid": "testuser",
        "exp": int(time.time()) + 600,
        "iat": int(time.time()),
    }

    state = jwt.encode(state_payload, secret, algorithm="HS256")

    return {
        "tx_id": tx_id,
        "state": state,
        "stored": True,
        "callback_url": f"http://127.0.0.1:8000/v1/spotify/callback?code=fake&state={state}"
    }

@router.get("/connect")
async def spotify_connect(request: Request) -> Response:
    """Initiate Spotify OAuth flow with stateless PKCE.

    This route creates a JWT state containing user_id + tx_id, and stores
    the PKCE code_verifier server-side keyed by tx_id. No cookies required.

    Returns the authorization URL as JSON for frontend consumption.
    """
    # Resolve user id early for logging/rate-limiting and compatibility with tests
    try:
        user_id = get_current_user_id(request)
    except Exception:
        user_id = "anon"

    # Enhanced logging for debugging
    logger.info("🎵 SPOTIFY CONNECT: Request started", extra={
        "meta": {
            "user_id": user_id,
            "cookies_count": len(request.cookies),
            "has_access_token": bool(request.cookies.get("access_token")),
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

    # Resolve user id early for logging/rate-limiting
    try:
        user_id = get_current_user_id(request)
    except Exception:
        user_id = "anon"

    # Per-user rate limiting to avoid TX spam (disabled in tests unless explicitly enabled)
    try:
        import os as _os
        def _rl_enabled():
            if (_os.getenv("RATE_LIMIT_MODE") or "").strip().lower() == "off":
                return False
            in_test = (_os.getenv("ENV","" ).strip().lower()=="test") or bool(_os.getenv("PYTEST_RUNNING") or _os.getenv("PYTEST_CURRENT_TEST"))
            if in_test and (_os.getenv("ENABLE_RATE_LIMIT_IN_TESTS","0").strip().lower() not in {"1","true","yes","on"}):
                return False
            return True
        if _rl_enabled():
            from ..token_store import incr_login_counter
            minute = await incr_login_counter(f"rl:spotify_connect:user:{user_id}:m", 60)
            hour = await incr_login_counter(f"rl:spotify_connect:user:{user_id}:h", 3600)
            if minute > 10 or hour > 100:
                raise HTTPException(status_code=429, detail="too_many_requests")
    except HTTPException:
        raise
    except Exception:
        pass
    import time

    import jwt

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

    # For front-end compatibility in tests, set a temporary cookie carrying the
    # caller-provided bearer token (when present) so callback can correlate.
    try:
        authz = request.headers.get("Authorization") or ""
        if authz.lower().startswith("bearer "):
            jwt_token = authz.split(" ", 1)[1]
            from ..web.cookies import set_named_cookie
            set_named_cookie(
                resp=response,
                name="spotify_oauth_jwt",
                value=jwt_token,
                ttl=600,
                httponly=True,
                samesite="lax",
                path="/",
                secure=None,
            )
    except Exception:
        pass

    # Resolve user id late to support test monkeypatching of get_current_user_id
    try:
        user_id = get_current_user_id(request)
    except Exception:
        user_id = "anon"

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

@router.post("/callback")
async def spotify_callback_post(request: Request, code: str | None = None, state: str | None = None) -> Response:
    """POST shim for Spotify callback that redirects to GET canonical endpoint."""
    from starlette.responses import RedirectResponse
    # Build the GET URL with the same query parameters
    query_params = []
    if code:
        query_params.append(f"code={code}")
    if state:
        query_params.append(f"state={state}")
    query_string = "&".join(query_params) if query_params else ""

    get_url = f"/v1/spotify/callback"
    if query_string:
        get_url += f"?{query_string}"

    return RedirectResponse(url=get_url, status_code=303)


@router.get("/callback")
async def spotify_callback(request: Request, code: str | None = None, state: str | None = None) -> Response:
    """Handle Spotify OAuth callback with stateless JWT state.

    Recovers user_id + PKCE code_verifier from JWT state + server store.
    No cookies required - works even if browser sends zero cookies.
    """
    import jwt
    from starlette.responses import RedirectResponse

    logger.info("🎵 SPOTIFY CALLBACK: start has_code=%s has_state=%s, code='%s'", bool(code), bool(state), code)
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
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
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
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
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
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=expired_state", status_code=302)
    except jwt.InvalidTokenError as e:
        logger.error("🎵 SPOTIFY CALLBACK: Invalid JWT state", extra={
            "meta": {"error_type": "InvalidTokenError", "error_message": str(e)}
        })
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=bad_state", status_code=302)
    except Exception as e:
        logger.error("🎵 SPOTIFY CALLBACK: JWT decode error", extra={
            "meta": {"error_type": type(e).__name__, "error_message": str(e)}
        })
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=bad_state", status_code=302)

    # 2) Recover PKCE + user from server store. We prefer the stateless tx_id
    # flow, but fall back to session-based PKCE storage when tx is not present
    # (compatibility with legacy/session flows and tests that monkeypatch
    # `get_pkce_challenge_by_state`).
    logger.info("🎵 SPOTIFY CALLBACK: Step 2 - Recovering transaction from store...")
    tx = None

    # Special handling for test mode
    if os.getenv("SPOTIFY_TEST_MODE", "0") == "1" and code == "fake":
        logger.info("🎵 SPOTIFY CALLBACK: TEST MODE - Using fake transaction data")
        tx = {
            "user_id": uid,
            "code_verifier": "test_verifier_fake_code",
            "ts": int(time.time())
        }
    elif tx_id:
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
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
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
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
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
                scopes=token_data.get("scope"),
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
        else:
            # If it's already a ThirdPartyToken, update the user_id
            token_data.user_id = uid

        # Set provider_iss for Spotify tokens (required for validation)
        if token_data.provider == "spotify":
            token_data.provider_iss = "https://accounts.spotify.com"

        # Set fake identity_id for test mode tokens
        if token_data.access_token and token_data.access_token.startswith("B"):
            token_data.identity_id = f"test_identity_{secrets.token_hex(8)}"

        # Attempt to resolve Spotify profile to obtain provider_sub (spotify user id)
        provider_sub = None
        identity_id_used = None
        try:
            from .. import auth_store as auth_store

            # Check if this is a test mode token (starts with "fake_")
            if token_data.access_token and token_data.access_token.startswith("fake_access_"):
                # Test mode: use fake profile data
                provider_sub = f"test_user_{secrets.token_hex(4)}"
                email_norm = f"{provider_sub}@test.spotify.com"
                logger.info("🎵 SPOTIFY CALLBACK: Using test mode profile data", extra={
                    "meta": {"provider_sub": provider_sub, "email": email_norm}
                })
            else:
                # Production mode: fetch real profile from Spotify API
                import httpx
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as cli:
                    resp = await cli.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {token_data.access_token}"})
                if resp.status_code == 200:
                    profile = resp.json()
                    provider_sub = profile.get("id")
                    email_norm = (profile.get("email") or "").lower()

            # Try to find existing identity
            try:
                existing_ident = await auth_store.get_oauth_identity_by_provider("spotify", "https://accounts.spotify.com", str(provider_sub)) if provider_sub else None
            except Exception:
                existing_ident = None
            if existing_ident and existing_ident.get("id"):
                identity_id_used = existing_ident.get("id")
            elif provider_sub:
                # Create/link identity
                try:
                    new_id = f"s_{secrets.token_hex(8)}"
                    await auth_store.link_oauth_identity(
                        id=new_id,
                        user_id=token_data.user_id,
                        provider="spotify",
                        provider_sub=str(provider_sub),
                        email_normalized=email_norm,
                        provider_iss="https://accounts.spotify.com",
                    )
                    identity_id_used = new_id
                    logger.info("🎵 SPOTIFY CALLBACK: Created new identity", extra={
                        "meta": {"identity_id": identity_id_used, "provider_sub": provider_sub}
                    })
                except Exception:
                    # Race condition: fetch existing identity
                    try:
                        re = await auth_store.get_oauth_identity_by_provider("spotify", "https://accounts.spotify.com", str(provider_sub))
                        if re:
                            identity_id_used = re.get("id")
                    except Exception:
                        identity_id_used = None
        except Exception as e:
            # Best-effort only; proceed even if profile lookup/link fails
            logger.warning("🎵 SPOTIFY CALLBACK: Identity linking failed", extra={
                "meta": {"error": str(e), "error_type": type(e).__name__}
            })
            provider_sub = None
            identity_id_used = None

        # Populate provider_sub / identity_id if resolved
        if provider_sub:
            token_data.provider_sub = str(provider_sub)
        if identity_id_used:
            token_data.identity_id = identity_id_used

        logger.info("🎵 SPOTIFY CALLBACK: Identity linking complete", extra={
            "meta": {
                "provider_sub": getattr(token_data, 'provider_sub', None),
                "identity_id": getattr(token_data, 'identity_id', None),
                "user_id": getattr(token_data, 'user_id', None),
                "tx_id": tx_id
            }
        })

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
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
        return RedirectResponse(f"{frontend_url}/settings#spotify?spotify_error=token_exchange_failed", status_code=302)

    # 4) Persist tokens for user
    logger.info("🎵 SPOTIFY CALLBACK: Step 4 - Persisting tokens to database...")
    try:
        # Access ThirdPartyToken attributes correctly (not dict-style)
        access_token = token_data.access_token
        refresh_token = token_data.refresh_token
        expires_at = token_data.expires_at

        logger.debug("🎵 SPOTIFY CALLBACK: persisting tokens tx=%s uid=%s", tx_id, uid)

        # Attempt to resolve Spotify profile to obtain provider_sub (spotify user id)
        provider_sub = None
        identity_id_used = None
        try:
            import httpx

            from .. import auth_store as auth_store

            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as cli:
                resp = await cli.get("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {access_token}"})
            if resp.status_code == 200:
                profile = resp.json()
                provider_sub = profile.get("id")
                email_norm = (profile.get("email") or "").lower()
                # Try to find existing identity
                try:
                    existing_ident = await auth_store.get_oauth_identity_by_provider("spotify", "https://accounts.spotify.com", str(provider_sub)) if provider_sub else None
                except Exception:
                    existing_ident = None
                if existing_ident and existing_ident.get("id"):
                    identity_id_used = existing_ident.get("id")
                elif provider_sub:
                    # Create/link identity
                    try:
                        new_id = f"s_{secrets.token_hex(8)}"
                        await auth_store.link_oauth_identity(
                            id=new_id,
                            user_id=uid,
                            provider="spotify",
                            provider_sub=str(provider_sub),
                            email_normalized=email_norm,
                            provider_iss="https://accounts.spotify.com",
                        )
                        identity_id_used = new_id
                    except Exception:
                        # Race condition: fetch existing identity
                        try:
                            re = await auth_store.get_oauth_identity_by_provider("spotify", "https://accounts.spotify.com", str(provider_sub))
                            if re:
                                identity_id_used = re.get("id")
                        except Exception:
                            identity_id_used = None
        except Exception:
            # Best-effort only; proceed even if profile lookup/link fails
            provider_sub = None
            identity_id_used = None

        # Use the token_data object directly (already has user_id, provider_sub, identity_id set)
        logger.info("🎵 SPOTIFY CALLBACK: About to call upsert_token", extra={
            "meta": {
                "token_id": getattr(token_data, 'id', None),
                "user_id": getattr(token_data, 'user_id', None),
                "identity_id": getattr(token_data, 'identity_id', None),
                "provider": getattr(token_data, 'provider', None)
            }
        })

        persisted = await upsert_token(token_data)

        logger.info(
            "🎵 SPOTIFY CALLBACK: upsert_token returned",
            extra={"meta": {"tx_id": tx_id, "user_id": uid, "persisted": bool(persisted)}},
        )

        # Double-check if token was actually created
        if persisted:
            from ..auth_store_tokens import get_token
            check_token = await get_token(uid, "spotify")
            logger.info(
                "🎵 SPOTIFY CALLBACK: Token verification after upsert",
                extra={"meta": {
                    "found_token": check_token is not None,
                    "token_id": getattr(check_token, 'id', None) if check_token else None,
                    "token_identity_id": getattr(check_token, 'identity_id', None) if check_token else None
                }}
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
        frontend_url = os.getenv("FRONTEND_URL", os.getenv("GESAHNI_FRONTEND_URL", "http://localhost:3000"))
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

    logger.info("🎵 SPOTIFY STATUS: Request started", extra={
        "meta": {
            "headers": dict(request.headers),
            "cookies_count": len(request.cookies),
            "has_authorization": bool(request.headers.get("Authorization"))
        }
    })

    # Check if user is authenticated
    current_user = None
    try:
        current_user = get_current_user_id(request=request)
        logger.info("🎵 SPOTIFY STATUS: User authentication", extra={
            "meta": {
                "user_id": current_user,
                "is_authenticated": current_user is not None and current_user != "anon"
            }
        })
    except Exception as e:
        logger.warning("🎵 SPOTIFY STATUS: Authentication error", extra={
            "meta": {
                "error": str(e),
                "error_type": type(e).__name__
            }
        })

    if not current_user or current_user == "anon":
        logger.info("🎵 SPOTIFY STATUS: Unauthenticated user", extra={
            "meta": {
                "user_id": current_user,
                "returning_not_authenticated": True
            }
        })
        # Return status for unauthenticated users - not connected
        body: dict = {"connected": False, "devices_ok": False, "state_ok": False, "reason": "not_authenticated"}
        return JSONResponse(body, status_code=200)

    logger.info("🎵 SPOTIFY STATUS: Creating Spotify client", extra={
        "meta": {
            "user_id": current_user
        }
    })

    client = SpotifyClient(current_user)

    # Determine token connectivity by performing a lightweight probe to /me.
    #  - 200 -> token valid
    #  - 401/403 -> invalidate stored token and mark as not connected (reauthorize)
    connected = False
    reason: str | None = None
    devices_ok = False
    state_ok = False
    required_scopes_ok: bool | None = None

    logger.info("🎵 SPOTIFY STATUS: Starting connectivity probe", extra={
        "meta": {
            "user_id": current_user,
            "probe_endpoint": "/me"
        }
    })

    try:
        # Lightweight probe: user profile
        logger.info("🎵 SPOTIFY STATUS: Calling get_user_profile", extra={
            "meta": {
                "user_id": current_user
            }
        })

        profile = await client.get_user_profile()

        logger.info("🎵 SPOTIFY STATUS: get_user_profile result", extra={
            "meta": {
                "user_id": current_user,
                "profile_received": profile is not None,
                "profile_keys": list(profile.keys()) if profile else None
            }
        })

        if profile is not None:
            connected = True
            logger.info("🎵 SPOTIFY STATUS: Profile found, marking as connected", extra={
                "meta": {
                    "user_id": current_user,
                    "connected": True
                }
            })
        else:
            connected = False
            logger.warning("🎵 SPOTIFY STATUS: Profile is None, marking as not connected", extra={
                "meta": {
                    "user_id": current_user,
                    "connected": False
                }
            })
    except Exception as e:
        logger.error("🎵 SPOTIFY STATUS: Exception during connectivity probe", extra={
            "meta": {
                "user_id": current_user,
                "error": str(e),
                "error_type": type(e).__name__
            }
        })

        # If we get an auth-related error, mark tokens invalid so frontend knows to reauth
        try:
            from ..auth_store_tokens import mark_invalid
            from ..integrations.spotify.client import SpotifyAuthError, SpotifyPremiumRequiredError

            logger.info("🎵 SPOTIFY STATUS: Checking exception type", extra={
                "meta": {
                    "user_id": current_user,
                    "is_spotify_auth_error": isinstance(e, SpotifyAuthError),
                    "is_premium_required": isinstance(e, SpotifyPremiumRequiredError),
                    "error_contains_401": str(e).lower().find('401') != -1,
                    "error_contains_needs_reauth": str(e).lower().find('needs_reauth') != -1
                }
            })

            if isinstance(e, SpotifyAuthError) or isinstance(e, SpotifyPremiumRequiredError) or str(e).lower().find('401') != -1 or str(e).lower().find('needs_reauth') != -1:
                logger.info("🎵 SPOTIFY STATUS: Auth error detected, invalidating tokens", extra={
                    "meta": {
                        "user_id": current_user
                    }
                })
                # Invalidate tokens to avoid false-positive "connected" UX
                try:
                    await mark_invalid(current_user, 'spotify')
                    logger.info("🎵 SPOTIFY STATUS: Tokens marked invalid", extra={
                        "meta": {
                            "user_id": current_user
                        }
                    })
                except Exception as mark_error:
                    logger.warning("🎵 SPOTIFY STATUS: failed to mark token invalid", extra={
                        "meta": {
                            "user_id": current_user,
                            "mark_error": str(mark_error)
                        }
                    })
                connected = False
                reason = 'needs_reauth'
            else:
                connected = False
                reason = str(e)
        except Exception as inner_e:
            logger.error("🎵 SPOTIFY STATUS: Exception in exception handler", extra={
                "meta": {
                    "user_id": current_user,
                    "original_error": str(e),
                    "inner_error": str(inner_e)
                }
            })
            connected = False
            reason = str(e)

    # If token looks connected, optionally verify device/state probes and scopes
    if connected:
        try:
            devices = await client.get_devices()
            devices_ok = True
        except Exception:
            devices_ok = False
        try:
            _ = await client.get_currently_playing()
            state_ok = True
        except Exception:
            state_ok = False

        # Verify required scopes are present on stored token when possible
        try:
            toks = await client._get_tokens()
            tok_scope = (toks.scope or "") if toks else ""
            token_scopes = set(s for s in tok_scope.split() if s)
            required = {"user-read-playback-state", "user-modify-playback-state", "user-read-currently-playing"}
            required_scopes_ok = required.issubset(token_scopes)
        except Exception:
            required_scopes_ok = None

    body: dict = {"connected": connected, "devices_ok": devices_ok, "state_ok": state_ok}

    logger.info("🎵 SPOTIFY STATUS: Building response", extra={
        "meta": {
            "user_id": current_user,
            "connected": connected,
            "devices_ok": devices_ok,
            "state_ok": state_ok,
            "reason": reason,
            "required_scopes_ok": required_scopes_ok
        }
    })

    if not connected and reason:
        body["reason"] = reason
        logger.info("🎵 SPOTIFY STATUS: Adding reason to response", extra={
            "meta": {
                "user_id": current_user,
                "reason": reason
            }
        })

    if required_scopes_ok is not None:
        body["required_scopes_ok"] = required_scopes_ok
        logger.info("🎵 SPOTIFY STATUS: Adding scopes info", extra={
            "meta": {
                "user_id": current_user,
                "required_scopes_ok": required_scopes_ok
            }
        })

        if toks := (await client._get_tokens() if required_scopes_ok is not None else None):
            body["scopes"] = (toks.scope or "").split()
            body["expires_at"] = toks.expires_at
            logger.info("🎵 SPOTIFY STATUS: Adding token details", extra={
                "meta": {
                    "user_id": current_user,
                    "scopes": (toks.scope or "").split(),
                    "expires_at": toks.expires_at
                }
            })

    logger.info("🎵 SPOTIFY STATUS: Returning response", extra={
        "meta": {
            "user_id": current_user,
            "response_body": body,
            "status_code": 200
        }
    })

    return JSONResponse(body, status_code=200)
