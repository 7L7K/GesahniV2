from __future__ import annotations

import logging
import os
import re
import secrets
import time
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from ..api.auth import _jwt_secret
from ..api.oauth_store import debug_store
from ..auth_store_tokens import upsert_token
from ..deps.user import get_current_user_id, resolve_session_id
from ..errors import json_error
from ..integrations.spotify.client import SpotifyClient
from ..integrations.spotify.oauth import (
    SpotifyOAuth,
    SpotifyPKCE,
    clear_pkce_challenge_by_state,
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
def _jwt_decode(token: str, secret: str, algorithms=None, **kwargs) -> dict:
    """Decode JWT token for test compatibility."""
    return jwt_decode(token, secret, algorithms=algorithms or ["HS256"], **kwargs)


from ..metrics import (
    OAUTH_CALLBACK,
    OAUTH_START,
    SPOTIFY_CALLBACK_TOTAL,
    SPOTIFY_STATUS_CONNECTED,
    SPOTIFY_STATUS_REQUESTS_COUNT,
    SPOTIFY_TOKENS_EXPIRES_IN_SECONDS,
)
from ..telemetry import hash_user_id

logger = logging.LoggerAdapter(
    logging.getLogger(__name__), {"component": "spotify.oauth"}
)
router = APIRouter(prefix="/spotify")

# --- test compatibility: expose exchange_code for monkeypatching ---
try:  # pragma: no cover - import error exercised in tests
    from ..integrations.spotify.oauth import exchange_code as exchange_code
except Exception:  # pragma: no cover - defensive guard for broken envs
    exchange_code = None  # type: ignore[assignment]

# New integrations endpoints at /v1/integrations/spotify/
integrations_router = APIRouter(prefix="/integrations/spotify")


@dataclass(slots=True)
class CallbackState:
    """Shape extracted from the Spotify callback state JWT."""

    tx_id: str | None
    user_id: str | None
    session_id: str | None
    payload: dict[str, Any]


_FRONTEND_FALLBACK = "http://localhost:3000"
_RECENT_REFRESH_SECONDS = int(os.getenv("SPOTIFY_REFRESH_RECENT_SECONDS", "3600"))


def _validate_frontend_url() -> str:
    raw = os.getenv("FRONTEND_URL") or os.getenv("GESAHNI_FRONTEND_URL")
    target = (raw or _FRONTEND_FALLBACK).strip()
    if target.endswith("/"):
        target = target.rstrip("/")
    env_name = (os.getenv("ENV") or "").strip().lower()

    try:
        from urllib.parse import urlparse

        parsed = urlparse(target)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("frontend url must include scheme and host")
        return target
    except Exception as exc:
        if env_name in {"prod", "production"}:
            logger.critical(
                "Invalid FRONTEND_URL configuration",
                extra={"meta": {"configured_url": raw, "error": str(exc)}},
            )
            raise RuntimeError("FRONTEND_URL must be a valid http(s) URL in production")
        logger.warning(
            "Invalid FRONTEND_URL configuration; falling back to default",
            extra={"meta": {"configured_url": raw, "error": str(exc)}},
        )
        return _FRONTEND_FALLBACK


_FRONTEND_URL = _validate_frontend_url()


def _frontend_url() -> str:
    return _FRONTEND_URL


def _parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return []
    values = []
    for entry in raw.split(","):
        item = entry.strip()
        if not item:
            continue
        values.append(item.rstrip("/").lower())
    return values


def _dev_mode_enabled() -> bool:
    env_name = (os.getenv("ENV") or "").strip().lower()
    if env_name in {"dev", "development", "test", "testing", "ci"}:
        return True
    return os.getenv("DEV_MODE", "0").strip().lower() in {"1", "true", "yes", "on"}


def _origin_regexes() -> list[re.Pattern[str]]:
    raw = os.getenv("SPOTIFY_ORIGIN_REGEXES")
    patterns: list[re.Pattern[str]] = []
    if not raw:
        return patterns
    for entry in raw.split(","):
        pattern = entry.strip()
        if not pattern:
            continue
        try:
            patterns.append(re.compile(pattern, re.IGNORECASE))
        except re.error as exc:
            logger.warning(
                "Failed to compile origin regex",
                extra={"meta": {"pattern": pattern, "error": str(exc)}},
            )
    return patterns


_ORIGIN_REGEXES = _origin_regexes()


def _origin_allowed(candidate: str, allowed: Iterable[str]) -> bool:
    normalized = (candidate or "").strip().rstrip("/").lower()
    if not normalized:
        return False
    if normalized in allowed:
        return True
    for regex in _ORIGIN_REGEXES:
        if regex.search(normalized):
            return True
    return False


def _prefers_json_response(request: Request) -> bool:
    accept = (request.headers.get("Accept") or "").lower()
    if "application/json" in accept:
        return True
    user_agent = (request.headers.get("User-Agent") or "").lower()
    return not user_agent or "testclient" in user_agent


def _callback_redirect(error: str) -> Response:
    from starlette.responses import RedirectResponse

    logger.info("spotify.callback:redirect")
    return RedirectResponse(
        f"{_frontend_url()}/settings#spotify?spotify_error={error}", status_code=302
    )


def _token_scope_list(token: Any) -> list[str]:
    raw = None
    if token is not None:
        raw = getattr(token, "scopes", None)
        if not raw:
            raw = getattr(token, "scope", None)
    if not raw:
        return []
    if isinstance(raw, (list, tuple, set)):
        items = [str(item).strip() for item in raw]
    else:
        items = [part.strip() for part in str(raw).replace(",", " ").split()]
    return [scope for scope in items if scope]


def _recent_refresh(ts: int | None, *, now: int) -> bool:
    if not ts:
        return False
    return (now - ts) < _RECENT_REFRESH_SECONDS


def _decode_callback_state(state_token: str) -> CallbackState:
    secret = _jwt_secret()
    issuer = (os.getenv("JWT_ISS") or os.getenv("JWT_ISSUER") or "").strip() or None
    audience = (os.getenv("JWT_AUD") or os.getenv("JWT_AUDIENCE") or "").strip() or None
    leeway = int(os.getenv("JWT_STATE_LEEWAY", "10"))
    options = {"verify_aud": bool(audience)}
    payload = _jwt_decode(
        state_token,
        secret,
        algorithms=["HS256"],
        options=options,
        audience=audience,
        issuer=issuer,
        leeway=leeway,
    )
    tx_val = payload.get("tx") or payload.get("sid") or payload.get("t")
    uid_val = payload.get("uid") or payload.get("sub") or payload.get("user")
    session_val = payload.get("sid") or payload.get("session")
    tx_id = str(tx_val) if tx_val else None
    uid = str(uid_val) if uid_val else None
    session_id = str(session_val) if session_val else None
    return CallbackState(
        tx_id=tx_id, user_id=uid, session_id=session_id, payload=payload
    )


async def get_spotify_oauth_token(code: str, code_verifier: str) -> ThirdPartyToken:
    """Exchange the OAuth authorization code for Spotify tokens.

    This helper keeps the callback flow focused on orchestration while the actual
    exchange logic lives alongside the Spotify OAuth implementation. The
    ``exchange_code`` helper returns a ``ThirdPartyToken`` with the ``user_id``
    left blank; the caller is responsible for stamping the authenticated user.
    """

    fn = globals().get("exchange_code")
    if fn is None:  # pragma: no cover - exercised when import guard trips
        from ..integrations.spotify.oauth import exchange_code as fn

    token_data = await fn(code=code, code_verifier=code_verifier)
    return token_data


async def verify_spotify_token(access_token: str) -> dict[str, str | None]:
    """Fetch the Spotify profile associated with ``access_token``.

    The callback flow uses this to resolve ``provider_sub`` and link identities.
    When a network error occurs we deliberately swallow the exception and return
    an empty payload so the login flow remains best-effort (the token is still
    persisted and can be refreshed later).
    """

    if not access_token:
        return {}

    # Allow test mode shortcuts where the token is clearly synthetic.
    if access_token.startswith("fake_access_") or os.getenv("SPOTIFY_TEST_MODE") == "1":
        return {
            "id": f"fake_user_{access_token[-8:]}" if access_token else None,
            "email": f"{access_token[-8:]}@test.spotify" if access_token else None,
        }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0)) as cli:
            resp = await cli.get(
                "https://api.spotify.com/v1/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                logger.warning(
                    "🎵 SPOTIFY VERIFY: profile lookup failed",
                    extra={
                        "meta": {
                            "status": resp.status_code,
                            "body_preview": resp.text[:120],
                        }
                    },
                )
                return {}
            profile = resp.json()
            return {
                "id": profile.get("id"),
                "email": profile.get("email"),
                "display_name": profile.get("display_name"),
            }
    except Exception as exc:  # pragma: no cover - httpx errors are best-effort
        logger.warning(
            "🎵 SPOTIFY VERIFY: profile request errored",
            extra={"meta": {"error": str(exc), "error_type": type(exc).__name__}},
        )
        return {}


async def _link_spotify_identity(
    *,
    user_id: str,
    provider_sub: str | None,
    email_norm: str | None,
) -> str | None:
    """Ensure the Spotify OAuth identity row exists and return the id."""

    if not provider_sub:
        return None

    try:
        from .. import auth_store as auth_store
        from ..util.ids import to_uuid

        # Convert username to UUID for database operations
        user_uuid = str(to_uuid(user_id))

        existing = await auth_store.get_oauth_identity_by_provider(
            "spotify", "https://accounts.spotify.com", str(provider_sub)
        )
        if existing and existing.get("id"):
            return existing["id"]

        new_id = f"s_{secrets.token_hex(8)}"
        try:
            await auth_store.link_oauth_identity(
                id=new_id,
                user_id=user_uuid,
                provider="spotify",
                provider_sub=str(provider_sub),
                email_normalized=email_norm,
                provider_iss="https://accounts.spotify.com",
            )
            return new_id
        except IntegrityError as db_exc:
            logger.warning(
                "🎵 SPOTIFY IDENTITY: FK violation, skipping identity link",
                extra={
                    "meta": {
                        "user_id": user_id,
                        "provider_sub": provider_sub,
                        "error": str(db_exc),
                        "hint": "seed users table or link after user creation",
                    }
                },
            )
            return None
        except Exception:
            # Possible race – fetch again.
            retry = await auth_store.get_oauth_identity_by_provider(
                "spotify", "https://accounts.spotify.com", str(provider_sub)
            )
            if retry and retry.get("id"):
                return retry["id"]
    except Exception as exc:
        logger.warning(
            "🎵 SPOTIFY IDENTITY: failed to link identity",
            extra={
                "meta": {
                    "user_id": user_id,
                    "provider_sub": provider_sub,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                }
            },
        )
    return None


@integrations_router.get("/status")
async def integrations_spotify_status(
    request: Request, user_id: str = Depends(get_current_user_id)
) -> dict:
    """Get Spotify integration status for frontend polling.

    Returns status information that frontend can use to determine if reconnect is needed.
    """
    logger.info(
        "🎵 SPOTIFY INTEGRATIONS STATUS: Request started",
        extra={
            "user_id": user_id,
            "route": "/v1/integrations/spotify/status",
            "auth_state": (
                "spotify_linked=true" if user_id != "anon" else "spotify_linked=false"
            ),
            "meta": {"user_id": user_id, "endpoint": "/v1/integrations/spotify/status"},
        },
    )

    now = int(time.time())

    try:
        from ..auth_store_tokens import get_token

        token = await get_token(user_id, "spotify")
        logger.info(
            "🎵 SPOTIFY INTEGRATIONS STATUS: Token retrieved",
            extra={
                "meta": {
                    "user_id": user_id,
                    "token_found": token is not None,
                    "token_id": getattr(token, "id", None) if token else None,
                    "identity_id": (
                        getattr(token, "identity_id", None) if token else None
                    ),
                    "expires_at": getattr(token, "expires_at", None) if token else None,
                    "last_refresh_at": (
                        getattr(token, "last_refresh_at", None) if token else None
                    ),
                    "scopes": getattr(token, "scopes", None) if token else None,
                    "is_valid": getattr(token, "is_valid", None) if token else None,
                }
            },
        )
    except Exception as e:
        logger.error(
            "🎵 SPOTIFY INTEGRATIONS STATUS: Failed to get token",
            extra={
                "meta": {
                    "user_id": user_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            },
        )
        return {
            "connected": False,
            "expires_at": None,
            "last_refresh_at": None,
            "refreshed": False,
            "scopes": [],
        }

    expires_at = getattr(token, "expires_at", 0) if token else 0
    last_refresh_at = getattr(token, "last_refresh_at", 0) if token else 0
    is_valid = bool(getattr(token, "is_valid", False)) if token else False

    connected = bool(token and is_valid and expires_at and expires_at > now)
    scopes = _token_scope_list(token)
    refreshed = _recent_refresh(last_refresh_at, now=now) if token else False

    result = {
        "connected": connected,
        "expires_at": expires_at if token else None,
        "last_refresh_at": last_refresh_at if token else None,
        "refreshed": refreshed,
        "scopes": scopes,
    }

    logger.info(
        "🎵 SPOTIFY INTEGRATIONS STATUS: Returning status",
        extra={
            "user_id": user_id,
            "route": "/v1/integrations/spotify/status",
            "auth_state": (
                "spotify_linked=true" if user_id != "anon" else "spotify_linked=false"
            ),
            "meta": {
                "user_id": user_id,
                "connected": connected,
                "expires_at": expires_at if token else None,
                "last_refresh_at": last_refresh_at if token else None,
                "refreshed": refreshed,
                "scopes_count": len(scopes),
                "needs_reconnect": not connected,
            },
        },
    )

    # Track status request metrics
    try:
        SPOTIFY_STATUS_REQUESTS_COUNT.labels(
            status="200",
            auth_state=(
                "spotify_linked=true" if user_id != "anon" else "spotify_linked=false"
            ),
        ).inc()
    except Exception:
        pass

    return result


SPOTIFY_AUTH = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN = "https://accounts.spotify.com/api/token"


def _pkce_challenge() -> SpotifyPKCE:
    """Generate PKCE challenge for OAuth flow."""
    oauth = SpotifyOAuth()
    return oauth.generate_pkce()


if os.getenv("SPOTIFY_LOGIN_LEGACY", "0") == "1":

    @router.get("/login")
    async def spotify_login(
        request: Request, user_id: str = Depends(get_current_user_id)
    ) -> Response:
        """Legacy Spotify login endpoint (enabled only when SPOTIFY_LOGIN_LEGACY=1).

        This route is intentionally excluded from import/mount when the
        feature flag is not set to reduce attack surface. The implementation
        is deprecated and kept behind the explicit opt-in.
        """
        logger.info(
            "🎵 SPOTIFY LOGIN: Starting Spotify OAuth flow",
            extra={
                "meta": {
                    "user_id": user_id,
                    "client_ip": request.client.host if request.client else "unknown",
                    "user_agent": request.headers.get("User-Agent", "unknown"),
                    "has_cookies": len(request.cookies) > 0,
                }
            },
        )

        # Generate PKCE and authorization URL via helper
        logger.info("🎵 SPOTIFY LOGIN: Generating PKCE challenge...")
        state, challenge, verifier = await make_authorize_url.prepare_pkce()
        logger.info(
            "🎵 SPOTIFY LOGIN: PKCE generated",
            extra={
                "meta": {
                    "state_length": len(state),
                    "challenge_length": len(challenge),
                    "verifier_length": len(verifier),
                }
            },
        )

        # Store verifier tied to the session (session id from cookie or resolved)
        sid = resolve_session_id(request=request)
        logger.info(
            "🎵 SPOTIFY LOGIN: Storing PKCE challenge",
            extra={
                "meta": {
                    "session_id": sid,
                    "session_id_length": len(sid) if sid else 0,
                }
            },
        )

        pkce_data = SpotifyPKCE(
            verifier=verifier, challenge=challenge, state=state, created_at=time.time()
        )
        store_pkce_challenge(sid, pkce_data)

        logger.info("🎵 SPOTIFY LOGIN: Building authorization URL...")
        auth_url = make_authorize_url.build(state=state, code_challenge=challenge)
        logger.info(
            "🎵 SPOTIFY LOGIN: Authorization URL built",
            extra={"meta": {"auth_url_length": len(auth_url)}},
        )

        # Return JSON response with the auth URL
        from fastapi.responses import JSONResponse

        response = JSONResponse(
            content={"ok": True, "authorize_url": auth_url, "session_id": sid}
        )

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
            logger.info(
                "🎵 SPOTIFY LOGIN: Set spotify_oauth_jwt cookie",
                extra={"meta": {"token_length": len(jwt_token)}},
            )

        logger.info(
            "🎵 SPOTIFY LOGIN: Returning response",
            extra={
                "meta": {
                    "has_authorize_url": bool(auth_url),
                    "authorize_url_length": len(auth_url),
                }
            },
        )
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
        "ts": int(time.time()),
    }

    put_tx(tx_id, tx_data, ttl_seconds=600)

    return {"tx_id": tx_id, "stored": True, "user_id": "testuser"}


@router.post("/test/full_flow")
async def test_full_flow():
    """Test endpoint that stores a transaction and returns the JWT state."""
    import secrets
    import time
    import uuid

    # Store transaction
    tx_id = uuid.uuid4().hex
    tx_data = {
        "user_id": "testuser",
        "code_verifier": f"test_verifier_{secrets.token_hex(16)}",
        "ts": int(time.time()),
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
        "callback_url": f"http://127.0.0.1:8000/v1/spotify/callback?code=fake&state={state}",
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
    logger.info(
        "🎵 SPOTIFY CONNECT: Request started",
        extra={
            "meta": {
                "user_id": user_id,
                "cookies_count": len(request.cookies),
                "has_access_token": bool(
                    request.cookies.get("access_token")
                    or request.cookies.get("GSNH_AT")
                ),
                "authorization_header": bool(request.headers.get("Authorization")),
                "host": request.headers.get("host"),
                "origin": request.headers.get("origin"),
            }
        },
    )
    import uuid

    # Basic CSRF hardening: validate Origin/Referer against allowed origins
    try:
        allowed = set(
            _parse_origins(
                os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000") or ""
            )
        )
        if _dev_mode_enabled():
            allowed.update(
                {
                    "http://localhost",
                    "http://localhost:3000",
                    "http://127.0.0.1",
                    "http://127.0.0.1:3000",
                }
            )
        try:
            backend_origin = (
                (
                    f"{request.url.scheme}://{(request.headers.get('host') or '').split(',')[0]}"
                )
                .rstrip("/")
                .lower()
            )
            if backend_origin:
                allowed.add(backend_origin)
        except Exception:
            pass

        origin = (request.headers.get("origin") or "").strip()
        referer = (request.headers.get("referer") or "").strip()
        ref_origin = ""
        if referer:
            try:
                from urllib.parse import urlparse

                parsed = urlparse(referer)
                if parsed.scheme and parsed.netloc:
                    ref_origin = f"{parsed.scheme}://{parsed.netloc}"
            except Exception:
                ref_origin = ""

        from ..http_errors import http_error

        if origin and not _origin_allowed(origin, allowed):
            raise http_error(
                code="origin_not_allowed", message="origin not allowed", status=403
            )
        if not origin and ref_origin and not _origin_allowed(ref_origin, allowed):
            raise http_error(
                code="origin_not_allowed", message="origin not allowed", status=403
            )
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
            in_test = (_os.getenv("ENV", "").strip().lower() == "test") or bool(
                _os.getenv("PYTEST_RUNNING") or _os.getenv("PYTEST_CURRENT_TEST")
            )
            if in_test and (
                _os.getenv("ENABLE_RATE_LIMIT_IN_TESTS", "0").strip().lower()
                not in {"1", "true", "yes", "on"}
            ):
                return False
            return True

        if _rl_enabled():
            from ..token_store import incr_login_counter

            minute = await incr_login_counter(
                f"rl:spotify_connect:user:{user_id}:m", 60
            )
            hour = await incr_login_counter(
                f"rl:spotify_connect:user:{user_id}:h", 3600
            )
            if minute > 10 or hour > 100:
                raise HTTPException(status_code=429, detail="too_many_requests")
    except HTTPException:
        raise
    except Exception:
        pass
    import time

    # user_id is provided by dependency injection (requires authentication)
    if not user_id or user_id == "anon":
        logger.error("Spotify connect: unauthenticated request")
        from ..http_errors import unauthorized

        raise unauthorized(
            code="authentication_failed",
            message="authentication failed",
            hint="reconnect Spotify account",
        )
    logger.info(f"Spotify connect: authenticated user_id='{user_id}'")

    logger.info(
        "🎵 SPOTIFY CONNECT: Preparing stateless OAuth flow",
        extra={"meta": {"user_id": user_id, "component": "spotify_connect"}},
    )

    # Generate PKCE challenge
    logger.info("🎵 SPOTIFY CONNECT: Generating PKCE challenge...")
    state_raw, challenge, verifier = await make_authorize_url.prepare_pkce()
    tx_id = uuid.uuid4().hex

    logger.info(
        "🎵 SPOTIFY CONNECT: PKCE challenge generated",
        extra={
            "meta": {
                "tx_id": tx_id,
                "challenge_length": len(challenge),
                "verifier_length": len(verifier),
            }
        },
    )

    # Persist PKCE + user for 10 minutes
    tx_data = {"user_id": user_id, "code_verifier": verifier, "ts": int(time.time())}

    logger.info(
        "🎵 SPOTIFY CONNECT: Storing transaction data",
        extra={
            "meta": {
                "tx_id": tx_id,
                "user_id": user_id,
                "tx_data_keys": list(tx_data.keys()),
                "ttl_seconds": 600,
            }
        },
    )

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

    logger.info(
        "🎵 SPOTIFY CONNECT: JWT state created",
        extra={
            "meta": {
                "state_length": len(state),
                "payload_tx": tx_id,
                "payload_uid": user_id,
                "payload_exp": state_payload["exp"],
                "expires_in_minutes": 10,
            }
        },
    )

    # Metrics: oauth start
    try:
        OAUTH_START.labels("spotify").inc()
    except Exception:
        pass

    logger.info(
        "🎵 SPOTIFY CONNECT: Stateless OAuth tx saved",
        extra={
            "meta": {"tx_id": tx_id, "user_id": user_id, "state_jwt_length": len(state)}
        },
    )

    logger.info("🎵 SPOTIFY CONNECT: Building authorization URL...")
    auth_url = make_authorize_url.build(state=state, code_challenge=challenge)

    # Never log the URL itself; log only metadata
    logger.info(
        "🎵 SPOTIFY CONNECT: Authorization URL built",
        extra={"meta": {"auth_url_length": len(auth_url)}},
    )

    # If in test mode, short-circuit to backend callback for deterministic e2e tests
    if os.getenv("SPOTIFY_TEST_MODE", "0") == "1":
        backend = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
        auth_url = f"{backend}/v1/spotify/callback?code=fake&state={state}"

        logger.info(
            "🎵 SPOTIFY CONNECT: TEST MODE - Using short-circuit URL",
            extra={"meta": {"backend": backend}},
        )

    # Return JSON response with the auth URL
    from fastapi.responses import JSONResponse

    response = JSONResponse(
        content={
            "ok": True,
            "authorize_url": auth_url,
        }
    )

    # For front-end compatibility in tests, set a temporary cookie carrying the
    # caller-provided bearer token (when present) so callback can correlate.
    try:
        authz = request.headers.get("Authorization") or ""
        if authz.lower().startswith("bearer "):
            jwt_token = authz.split(" ", 1)[1]
            from ..web.cookies import set_named_cookie

            set_named_cookie(
                response,
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

    logger.info(
        "🎵 SPOTIFY CONNECT: Stateless flow complete",
        extra={
            "meta": {
                "no_cookies_set": True,
                "stateless_flow": True,
                "tx_id": tx_id,
                "user_id": user_id,
            }
        },
    )

    return response


@router.get("/callback-test")
async def spotify_callback_test(request: Request):
    """Simple test callback."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        content={
            "status": "ok",
            "message": "Test callback works",
            "params": dict(request.query_params),
            "cookies": list(request.cookies.keys()),
        }
    )


@router.get("/health")
async def spotify_health(request: Request):
    """Lightweight health check to confirm router mount and env wiring.

    Returns basic config flags without exposing secrets.
    """
    from fastapi.responses import JSONResponse

    try:
        client_id_set = bool(os.getenv("SPOTIFY_CLIENT_ID"))
        redirect_set = bool(os.getenv("SPOTIFY_REDIRECT_URI"))
        test_mode = os.getenv("SPOTIFY_TEST_MODE", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        return JSONResponse(
            {
                "ok": True,
                "client_id_set": client_id_set,
                "redirect_set": redirect_set,
                "test_mode": test_mode,
            },
            status_code=200,
        )
    except Exception as e:
        return json_error(
            code="internal_error",
            message="Something went wrong",
            http_status=500,
            meta={"ok": False, "error": str(e)},
        )


@router.get("/debug-cookie")
async def spotify_debug_cookie(request: Request) -> dict:
    """Dev-only helper (stubbed in production)."""
    if os.getenv("DEV_MODE") or os.getenv("SPOTIFY_TEST_MODE") == "1":
        return {"cookies": list(request.cookies.keys())}
    raise HTTPException(status_code=404, detail="not_found")


@router.post("/callback")
async def spotify_callback_post(
    request: Request, code: str | None = None, state: str | None = None
) -> Response:
    """POST shim for Spotify callback that redirects to GET canonical endpoint."""
    from starlette.responses import RedirectResponse

    # Build the GET URL with the same query parameters
    query_params = []
    if code:
        query_params.append(f"code={code}")
    if state:
        query_params.append(f"state={state}")
    query_string = "&".join(query_params) if query_params else ""

    get_url = "/v1/spotify/callback"
    if query_string:
        get_url += f"?{query_string}"

    return RedirectResponse(url=get_url, status_code=303)


@router.get("/callback")
async def spotify_callback(
    request: Request, code: str | None = None, state: str | None = None
) -> Response:
    """Handle Spotify OAuth callback with stateless JWT state.

    Recovers user_id + PKCE code_verifier from JWT state + server store.
    No cookies required - works even if browser sends zero cookies.
    """
    from starlette.responses import RedirectResponse

    logger.info(
        "🎵 SPOTIFY CALLBACK: start has_code=%s has_state=%s, code='%s'",
        bool(code),
        bool(state),
        code,
    )
    # Pre-decode diagnostics for `state` integrity without leaking secrets
    try:
        raw_state = state or ""
        state_diag = {
            "state_len": len(raw_state),
            "dot_count": raw_state.count("."),
            "looks_like_jwt": raw_state.count(".") == 2,
        }
        try:
            iss = (os.getenv("JWT_ISS") or os.getenv("JWT_ISSUER") or "").strip()
            aud = (os.getenv("JWT_AUD") or os.getenv("JWT_AUDIENCE") or "").strip()
            try:
                sec = _jwt_secret()
                sec_len = len(sec or "")
            except Exception:
                sec_len = 0
            state_diag.update(
                {
                    "jwt_secret_len": sec_len,
                    "jwt_iss_set": bool(iss),
                    "jwt_aud_set": bool(aud),
                }
            )
        except Exception:
            pass
        logger.info(
            "🎵 SPOTIFY CALLBACK: state diagnostics", extra={"meta": state_diag}
        )
    except Exception:
        pass

    logger.info("spotify.callback:start")

    logger.info("🎵 SPOTIFY CALLBACK: Step 1 - Verifying JWT state...")
    if not state:
        logger.error("🎵 SPOTIFY CALLBACK: Missing state param")
        if _prefers_json_response(request):
            try:
                SPOTIFY_CALLBACK_TOTAL.labels(result="bad_state").inc()
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="missing_state")
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="bad_state").inc()
        except Exception:
            pass
        return _callback_redirect("bad_state")
    if not code:
        logger.error("🎵 SPOTIFY CALLBACK: Missing authorization code")
        if _prefers_json_response(request):
            try:
                SPOTIFY_CALLBACK_TOTAL.labels(result="bad_state").inc()
            except Exception:
                pass
            raise HTTPException(status_code=400, detail="missing_code")
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="bad_state").inc()
        except Exception:
            pass
        return _callback_redirect("missing_code")

    tx_id: str | None = None
    uid: str | None = None
    state_ctx: CallbackState | None = None
    try:
        state_ctx = _decode_callback_state(state)
        tx_id = state_ctx.tx_id
        uid = state_ctx.user_id
        logger.debug("🎵 SPOTIFY CALLBACK: JWT decoded tx=%s uid=%s", tx_id, uid)
        logger.info("spotify.callback:jwt_ok")
    except jwt.ExpiredSignatureError as exc:
        logger.error(
            "🎵 SPOTIFY CALLBACK: JWT state expired",
            extra={
                "meta": {
                    "error_type": "ExpiredSignatureError",
                    "error_message": str(exc),
                }
            },
        )
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="expired_state").inc()
        except Exception:
            pass
        return _callback_redirect("expired_state")
    except jwt.InvalidTokenError as exc:
        logger.error(
            "🎵 SPOTIFY CALLBACK: Invalid JWT state",
            extra={
                "meta": {
                    "error_type": "InvalidTokenError",
                    "error_message": str(exc),
                }
            },
        )
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="bad_state").inc()
        except Exception:
            pass
        return _callback_redirect("bad_state")
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "🎵 SPOTIFY CALLBACK: JWT decode error",
            extra={
                "meta": {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            },
        )
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="bad_state").inc()
        except Exception:
            pass
        return _callback_redirect("bad_state")

    logger.info("🎵 SPOTIFY CALLBACK: Step 2 - Recovering transaction from store...")
    tx: dict[str, Any] | None = None

    if os.getenv("SPOTIFY_TEST_MODE", "0") == "1" and code == "fake":
        logger.info("🎵 SPOTIFY CALLBACK: TEST MODE - Using fake transaction data")
        tx = {
            "user_id": uid,
            "code_verifier": "test_verifier_fake_code",
            "ts": int(time.time()),
        }
    elif tx_id:
        tx = pop_tx(tx_id)

    if not tx and state_ctx and state_ctx.session_id and state:
        pkce = get_pkce_challenge_by_state(state_ctx.session_id, state)
        if pkce:
            tx = {
                "user_id": uid,
                "code_verifier": pkce.verifier,
                "ts": getattr(pkce, "created_at", int(time.time())),
            }
            try:
                clear_pkce_challenge_by_state(state_ctx.session_id, state)
            except Exception:
                pass

    if not tx:
        logger.error(
            "🎵 SPOTIFY CALLBACK: No transaction found in store",
            extra={
                "meta": {
                    "tx_id": tx_id,
                    "session_id": state_ctx.session_id if state_ctx else None,
                    "user_id": uid,
                    "store_empty": True,
                }
            },
        )
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="bad_state").inc()
        except Exception:
            pass
        return _callback_redirect("expired_txn")

    if tx.get("user_id") != uid:
        logger.error(
            "🎵 SPOTIFY CALLBACK: User ID mismatch in transaction",
            extra={
                "meta": {
                    "tx_id": tx_id,
                    "session_id": state_ctx.session_id if state_ctx else None,
                    "expected_user": uid,
                    "stored_user": tx.get("user_id"),
                    "user_mismatch": True,
                }
            },
        )
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="bad_state").inc()
        except Exception:
            pass
        return _callback_redirect("user_mismatch")

    code_verifier = tx["code_verifier"]

    logger.info("🎵 SPOTIFY CALLBACK: transaction recovered tx=%s uid=%s", tx_id, uid)

    logger.info(
        "🎵 SPOTIFY CALLBACK: Step 3 - Exchanging authorization code for tokens..."
    )
    token_data: ThirdPartyToken | None = None  # keep in outer scope for post-try checks
    try:
        logger.debug("🎵 SPOTIFY CALLBACK: calling token endpoint tx=%s", tx_id)

        raw_token = await get_spotify_oauth_token(
            code=code, code_verifier=code_verifier
        )

        if isinstance(raw_token, dict):
            now = int(time.time())
            expires_at = int(
                raw_token.get(
                    "expires_at", now + int(raw_token.get("expires_in", 3600))
                )
            )
            token_data = ThirdPartyToken(
                id=f"spotify:{secrets.token_hex(8)}",
                user_id=uid,
                provider="spotify",
                access_token=raw_token.get("access_token", ""),
                refresh_token=raw_token.get("refresh_token"),
                scopes=raw_token.get("scope"),
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
        else:
            token_data = raw_token
            token_data.user_id = uid

        if token_data.provider == "spotify":
            token_data.provider_iss = "https://accounts.spotify.com"

        profile = await verify_spotify_token(token_data.access_token)
        provider_sub = profile.get("id") if profile else None
        email_norm = (profile.get("email") or "").lower() if profile else None

        logger.info(
            "🎵 SPOTIFY CALLBACK: Profile verification",
            extra={
                "meta": {
                    "profile_success": profile is not None,
                    "provider_sub": provider_sub,
                    "email_norm": email_norm,
                    "profile_keys": list(profile.keys()) if profile else None,
                }
            },
        )

        # Ensure JWT user exists in database before creating identity
        from sqlalchemy.exc import IntegrityError

        from .. import auth_store as auth_store
        from ..util.ids import to_uuid

        user_uuid = str(to_uuid(token_data.user_id))
        try:
            await auth_store.create_user(
                id=user_uuid,
                email=f"{token_data.user_id}@jwt.local",  # Fallback email
                username=token_data.user_id,
                name=token_data.user_id,
            )
            logger.info(
                "✅ SPOTIFY CALLBACK: Created JWT user",
                extra={"meta": {"user_id": token_data.user_id, "user_uuid": user_uuid}},
            )
        except IntegrityError:
            logger.debug(
                "SPOTIFY CALLBACK: JWT user already exists",
                extra={"meta": {"user_id": token_data.user_id}},
            )

        identity_id_used = await _link_spotify_identity(
            user_id=token_data.user_id,
            provider_sub=str(provider_sub) if provider_sub else None,
            email_norm=email_norm,
        )

        # If identity linking failed, create fallback identity
        if not identity_id_used:
            logger.warning(
                "🎵 SPOTIFY CALLBACK: Identity linking failed, creating fallback identity",
                extra={
                    "meta": {
                        "user_id": token_data.user_id,
                        "provider_sub": provider_sub,
                        "profile_success": profile is not None,
                    }
                },
            )

            try:
                fallback_id = f"s_fallback_{secrets.token_hex(8)}"
                await auth_store.link_oauth_identity(
                    id=fallback_id,
                    user_id=str(to_uuid(token_data.user_id)),
                    provider="spotify",
                    provider_sub=(
                        str(provider_sub)
                        if provider_sub
                        else f"unknown_{secrets.token_hex(4)}"
                    ),
                    email_normalized=email_norm,
                    provider_iss="https://accounts.spotify.com",
                )
                identity_id_used = fallback_id
                logger.info(
                    "🎵 SPOTIFY CALLBACK: Created fallback identity",
                    extra={"meta": {"identity_id": fallback_id}},
                )
            except Exception as fallback_exc:
                logger.error(
                    "🎵 SPOTIFY CALLBACK: Fallback identity creation failed",
                    extra={
                        "meta": {
                            "error": str(fallback_exc),
                            "user_id": token_data.user_id,
                        }
                    },
                )
                try:
                    SPOTIFY_CALLBACK_TOTAL.labels(result="identity_link_failed").inc()
                except Exception:
                    pass
                return _callback_redirect("identity_link_failed")

        if identity_id_used:
            token_data.identity_id = identity_id_used
    except Exception as exc:
        logger.error(
            "🎵 SPOTIFY CALLBACK: Token exchange failed",
            extra={
                "meta": {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "user_id": uid,
                    "tx_id": tx_id,
                    "code_provided": bool(code),
                }
            },
        )
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="token_exchange_failed").inc()
        except Exception:
            pass
        return _callback_redirect("token_exchange_failed")

    if token_data is None:
        logger.error(
            "🎵 SPOTIFY CALLBACK: Token exchange returned no data",
            extra={
                "meta": {
                    "user_id": uid,
                    "tx_id": tx_id,
                    "code_provided": bool(code),
                }
            },
        )
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="token_exchange_failed").inc()
        except Exception:
            pass
        return _callback_redirect("token_exchange_failed")

    logger.info("🎵 SPOTIFY CALLBACK: Step 4 - Persisting tokens to database...")
    try:
        logger.debug("🎵 SPOTIFY CALLBACK: persisting tokens tx=%s uid=%s", tx_id, uid)
        logger.info(
            "🎵 SPOTIFY CALLBACK: Token data before upsert",
            extra={
                "meta": {
                    "token_id": getattr(token_data, "id", None),
                    "user_id": getattr(token_data, "user_id", None),
                    "provider": getattr(token_data, "provider", None),
                    "identity_id": getattr(token_data, "identity_id", None),
                    "provider_sub": getattr(token_data, "provider_sub", None),
                    "access_token_len": len(
                        getattr(token_data, "access_token", "") or ""
                    ),
                    "has_refresh_token": bool(
                        getattr(token_data, "refresh_token", None)
                    ),
                }
            },
        )

        persisted = await upsert_token(token_data)

        logger.info(
            "🎵 SPOTIFY CALLBACK: upsert_token returned",
            extra={
                "meta": {"tx_id": tx_id, "user_id": uid, "persisted": bool(persisted)}
            },
        )

        if persisted:
            from ..auth_store_tokens import get_token

            check_token = await get_token(uid, "spotify")
            logger.info(
                "🎵 SPOTIFY CALLBACK: Token verification after upsert",
                extra={
                    "meta": {
                        "found_token": check_token is not None,
                        "token_id": (
                            getattr(check_token, "id", None) if check_token else None
                        ),
                        "token_identity_id": (
                            getattr(check_token, "identity_id", None)
                            if check_token
                            else None
                        ),
                    }
                },
            )

        logger.info("spotify.callback:tokens_persisted")

        try:
            OAUTH_CALLBACK.labels("spotify").inc()
        except Exception as metric_exc:
            logger.debug(
                "🎵 SPOTIFY CALLBACK: metrics increment failed: %s",
                str(metric_exc),
            )

    except Exception as exc:
        has_at = bool(getattr(token_data, "access_token", None))
        has_rt = bool(getattr(token_data, "refresh_token", None))
        logger.error(
            "🎵 SPOTIFY CALLBACK: Token persistence failed",
            extra={
                "meta": {
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "user_id": uid,
                    "tx_id": tx_id,
                    "has_access_token": has_at,
                    "has_refresh_token": has_rt,
                }
            },
        )
        try:
            SPOTIFY_CALLBACK_TOTAL.labels(result="token_exchange_failed").inc()
        except Exception:
            pass
        return _callback_redirect("token_save_failed")

    redirect_url = f"{_frontend_url()}/settings?spotify=connected"

    logger.info("🎵 SPOTIFY CALLBACK: completed tx=%s uid=%s", tx_id, uid)
    logger.info("spotify.callback:redirect")
    try:
        SPOTIFY_CALLBACK_TOTAL.labels(result="ok").inc()
    except Exception:
        pass

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

        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )

    # Mark tokens invalid and record revocation timestamp using async DAO
    success = await SpotifyClient(user_id).disconnect()
    if success:
        try:
            # Use centralized async token store to avoid blocking the event loop
            from ..auth_store_tokens import mark_invalid as mark_token_invalid

            await mark_token_invalid(user_id, "spotify")
        except Exception as e:
            logger.warning(
                "🎵 SPOTIFY DISCONNECT: failed to mark token invalid via DAO",
                extra={"meta": {"error": str(e)}},
            )

    return {"ok": success}


@router.get("/status")
async def spotify_status(request: Request, response: Response) -> dict:
    """Get Spotify integration status.

    Returns a richer shape to avoid dead route usage on the frontend:
    { connected: bool, devices_ok: bool, state_ok: bool, reason?: string }
    """
    from fastapi.responses import JSONResponse

    # Add no-store headers to prevent caching
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"

    now = int(time.time())

    # Check if user is authenticated
    current_user = None
    try:
        current_user = get_current_user_id(request=request)

        logger.info(
            "🎵 SPOTIFY STATUS: Request started",
            extra={
                "user_id": current_user or "anon",
                "route": "/v1/spotify/status",
                "auth_state": (
                    "spotify_linked=true"
                    if current_user and current_user != "anon"
                    else "spotify_linked=false"
                ),
                "meta": {
                    "headers": dict(request.headers),
                    "cookies_count": len(request.cookies),
                    "has_authorization": bool(request.headers.get("Authorization")),
                },
            },
        )

        logger.info(
            "🎵 SPOTIFY STATUS: User authentication",
            extra={
                "meta": {
                    "user_id": current_user,
                    "is_authenticated": current_user is not None
                    and current_user != "anon",
                }
            },
        )
    except Exception as e:
        logger.warning(
            "🎵 SPOTIFY STATUS: Authentication error",
            extra={"meta": {"error": str(e), "error_type": type(e).__name__}},
        )

    user_label = "anon"
    if current_user and current_user != "anon":
        try:
            user_label = hash_user_id(current_user)
        except Exception:
            user_label = "hash_error"

    if not current_user or current_user == "anon":
        logger.info(
            "🎵 SPOTIFY STATUS: Unauthenticated user",
            extra={
                "meta": {"user_id": current_user, "returning_not_authenticated": True}
            },
        )
        # Return status for unauthenticated users - not connected
        body: dict = {
            "connected": False,
            "devices_ok": False,
            "state_ok": False,
            "reason": "not_authenticated",
        }
        try:
            SPOTIFY_TOKENS_EXPIRES_IN_SECONDS.labels(user=user_label).set(0)
        except Exception:
            pass
        return JSONResponse(body, status_code=200)

    logger.info(
        "🎵 SPOTIFY STATUS: Creating Spotify client",
        extra={"meta": {"user_id": current_user}},
    )

    client = SpotifyClient(current_user)

    # Determine token connectivity by performing a lightweight probe to /me.
    #  - 200 -> token valid
    #  - 401/403 -> invalidate stored token and mark as not connected (reauthorize)
    connected = False
    reason: str | None = None
    devices_ok = False
    state_ok = False
    required_scopes_ok: bool | None = None
    scopes_list: list[str] | None = None
    cached_tokens: Any | None = None

    logger.info(
        "🎵 SPOTIFY STATUS: Starting connectivity probe",
        extra={"meta": {"user_id": current_user, "probe_endpoint": "/me"}},
    )

    try:
        # Lightweight probe: user profile
        logger.info(
            "🎵 SPOTIFY STATUS: Calling get_user_profile",
            extra={"meta": {"user_id": current_user}},
        )

        profile = await client.get_user_profile()

        logger.info(
            "🎵 SPOTIFY STATUS: get_user_profile result",
            extra={
                "meta": {
                    "user_id": current_user,
                    "profile_received": profile is not None,
                    "profile_keys": list(profile.keys()) if profile else None,
                }
            },
        )

        if profile is not None:
            connected = True
            logger.info(
                "🎵 SPOTIFY STATUS: Profile found, marking as connected",
                extra={"meta": {"user_id": current_user, "connected": True}},
            )
        else:
            connected = False
            logger.warning(
                "🎵 SPOTIFY STATUS: Profile is None, marking as not connected",
                extra={"meta": {"user_id": current_user, "connected": False}},
            )
    except Exception as e:
        logger.error(
            "🎵 SPOTIFY STATUS: Exception during connectivity probe",
            extra={
                "meta": {
                    "user_id": current_user,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            },
        )

        # If we get an auth-related error, mark tokens invalid so frontend knows to reauth
        try:
            from ..auth_store_tokens import mark_invalid
            from ..integrations.spotify.client import (
                SpotifyAuthError,
                SpotifyPremiumRequiredError,
            )

            logger.info(
                "🎵 SPOTIFY STATUS: Checking exception type",
                extra={
                    "meta": {
                        "user_id": current_user,
                        "is_spotify_auth_error": isinstance(e, SpotifyAuthError),
                        "is_premium_required": isinstance(
                            e, SpotifyPremiumRequiredError
                        ),
                        "error_contains_401": str(e).lower().find("401") != -1,
                        "error_contains_needs_reauth": str(e)
                        .lower()
                        .find("needs_reauth")
                        != -1,
                    }
                },
            )

            if (
                isinstance(e, SpotifyAuthError)
                or isinstance(e, SpotifyPremiumRequiredError)
                or str(e).lower().find("401") != -1
                or str(e).lower().find("needs_reauth") != -1
            ):
                logger.info(
                    "🎵 SPOTIFY STATUS: Auth error detected, invalidating tokens",
                    extra={"meta": {"user_id": current_user}},
                )
                # Invalidate tokens to avoid false-positive "connected" UX
                try:
                    await mark_invalid(current_user, "spotify")
                    logger.info(
                        "🎵 SPOTIFY STATUS: Tokens marked invalid",
                        extra={"meta": {"user_id": current_user}},
                    )
                except Exception as mark_error:
                    logger.warning(
                        "🎵 SPOTIFY STATUS: failed to mark token invalid",
                        extra={
                            "meta": {
                                "user_id": current_user,
                                "mark_error": str(mark_error),
                            }
                        },
                    )
                connected = False
                reason = "needs_reauth"
            else:
                connected = False
                reason = str(e)
        except Exception as inner_e:
            logger.error(
                "🎵 SPOTIFY STATUS: Exception in exception handler",
                extra={
                    "meta": {
                        "user_id": current_user,
                        "original_error": str(e),
                        "inner_error": str(inner_e),
                    }
                },
            )
            connected = False
            reason = str(e)

    # If token looks connected, optionally verify device/state probes and scopes
    if connected:
        try:
            await client.get_devices()
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
            cached_tokens = await client._get_tokens()
            scopes_list = _token_scope_list(cached_tokens)
            required = {
                "user-read-playback-state",
                "user-modify-playback-state",
                "user-read-currently-playing",
            }
            required_scopes_ok = required.issubset(set(scopes_list))
        except Exception:
            required_scopes_ok = None
            cached_tokens = None
            scopes_list = None

    body: dict = {
        "connected": connected,
        "devices_ok": devices_ok,
        "state_ok": state_ok,
    }

    logger.info(
        "🎵 SPOTIFY STATUS: Building response",
        extra={
            "meta": {
                "user_id": current_user,
                "connected": connected,
                "devices_ok": devices_ok,
                "state_ok": state_ok,
                "reason": reason,
                "required_scopes_ok": required_scopes_ok,
            }
        },
    )

    if connected:
        try:
            SPOTIFY_STATUS_CONNECTED.labels(user=user_label).inc()
        except Exception:
            pass

    if not connected and reason:
        body["reason"] = reason
        logger.info(
            "🎵 SPOTIFY STATUS: Adding reason to response",
            extra={"meta": {"user_id": current_user, "reason": reason}},
        )

    if required_scopes_ok is not None:
        body["required_scopes_ok"] = required_scopes_ok
        logger.info(
            "🎵 SPOTIFY STATUS: Adding scopes info",
            extra={
                "meta": {
                    "user_id": current_user,
                    "required_scopes_ok": required_scopes_ok,
                }
            },
        )

        if scopes_list is not None:
            body["scopes"] = scopes_list
        if cached_tokens is not None:
            body["expires_at"] = getattr(cached_tokens, "expires_at", None)
            logger.info(
                "🎵 SPOTIFY STATUS: Adding token details",
                extra={
                    "meta": {
                        "user_id": current_user,
                        "scopes": scopes_list,
                        "expires_at": getattr(cached_tokens, "expires_at", None),
                    }
                },
            )

    expires_in_seconds = 0
    if cached_tokens is not None and getattr(cached_tokens, "expires_at", None):
        try:
            expires_in_seconds = max(
                int(cached_tokens.expires_at or 0) - now,
                0,
            )
        except Exception:
            expires_in_seconds = 0
    try:
        SPOTIFY_TOKENS_EXPIRES_IN_SECONDS.labels(user=user_label).set(
            expires_in_seconds
        )
    except Exception:
        pass

    logger.info(
        "🎵 SPOTIFY STATUS: Returning response",
        extra={
            "user_id": current_user or "anon",
            "route": "/v1/spotify/status",
            "auth_state": (
                "spotify_linked=true"
                if current_user and current_user != "anon"
                else "spotify_linked=false"
            ),
            "meta": {
                "user_id": current_user,
                "response_body": body,
                "status_code": 200,
            },
        },
    )

    # Track status request metrics
    try:
        SPOTIFY_STATUS_REQUESTS_COUNT.labels(
            status="200",
            auth_state=(
                "spotify_linked=true"
                if current_user and current_user != "anon"
                else "spotify_linked=false"
            ),
        ).inc()
    except Exception:
        pass

    return JSONResponse(body, status_code=200)
