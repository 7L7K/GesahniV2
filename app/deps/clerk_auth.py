from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from fastapi import HTTPException, Request, WebSocket
from jwt import PyJWKClient

from ..security import jwt_decode

logger = logging.getLogger(__name__)


def _std_401() -> HTTPException:
    from ..http_errors import unauthorized
    return unauthorized(message="authentication required", hint="login or include Authorization header")


def _std_500(msg: str) -> HTTPException:
    return HTTPException(status_code=500, detail=msg)


def _read_env(name: str) -> str:
    return os.getenv(name, "").strip()


def _derive_issuer_and_jwks() -> tuple[str, str]:
    """Resolve Clerk issuer and JWKS URL from env.

    Supported env variables:
      - CLERK_JWKS_URL (preferred)
      - CLERK_ISSUER (e.g., https://<tenant>.clerk.accounts.dev)
      - CLERK_DOMAIN (e.g., <tenant>.clerk.accounts.dev)
    """
    jwks = _read_env("CLERK_JWKS_URL")
    if jwks:
        # Try to infer issuer by trimming suffix when using well-known path
        iss = _read_env("CLERK_ISSUER")
        if not iss and jwks.endswith("/.well-known/jwks.json"):
            iss = jwks[: -len("/.well-known/jwks.json")]
        return iss or "", jwks
    iss = _read_env("CLERK_ISSUER")
    if not iss:
        dom = _read_env("CLERK_DOMAIN")
        if dom:
            iss = f"https://{dom}"
    if not iss:
        return "", ""
    if iss.endswith("/.well-known/jwks.json"):
        return iss[: -len("/.well-known/jwks.json")], iss
    return iss, iss.rstrip("/") + "/.well-known/jwks.json"


@lru_cache(maxsize=1)
def _jwks_client() -> tuple[PyJWKClient, str, str | None]:
    iss, jwks_url = _derive_issuer_and_jwks()
    if not jwks_url:
        raise _std_500("clerk_not_configured")
    # Audience is optional; when provided we enforce it
    aud = _read_env("CLERK_AUDIENCE") or _read_env("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
    client = PyJWKClient(jwks_url)
    return client, iss, (aud or None)


def _extract_bearer_from_request(request: Request) -> str | None:
    token = None
    token_source = "none"

    # 1) Try access_token first (Authorization header or cookie)
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        token_source = "authorization_header"

    # Fallback to access_token cookie
    if not token:
        from ..web.cookies import read_access_cookie
        token = read_access_cookie(request)
        if token:
            token_source = "access_token_cookie"

    # 2) Try __session cookie if access_token failed
    if not token:
        from ..web.cookies import read_session_cookie
        token = read_session_cookie(request)
        if token:
            token_source = "__session_cookie"

    # Log which cookie/token source authenticated the request (debug level to reduce spam)
    if token:
        logger.debug(
            "auth.token_source",
            extra={
                "token_source": token_source,
                "has_token": bool(token),
                "token_length": len(token) if token else 0,
                "request_path": (
                    getattr(request, "url", {}).path
                    if hasattr(getattr(request, "url", {}), "path")
                    else "unknown"
                ),
                "auth_method": "clerk",
            },
        )

    return token


def _extract_bearer_from_ws(ws: WebSocket) -> str | None:
    token = None
    token_source = "none"

    # 1) Try access_token first (Authorization header, query param, or cookie)
    auth = ws.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth.split(" ", 1)[1]
        token_source = "authorization_header"

    # WS query param fallback for browser WebSocket handshakes
    if not token:
        try:
            qp = ws.query_params
            token = qp.get("access_token") or qp.get("token")
            if token:
                token_source = "websocket_query_param"
        except Exception:
            token = None

    # Cookie header fallback for WS handshakes
    if not token:
        try:
            raw_cookie = ws.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("access_token="):
                    token = p.split("=", 1)[1]
                    token_source = "websocket_access_token_cookie"
                    break
        except Exception:
            token = None

    # 2) Try __session cookie if access_token failed
    if not token:
        try:
            raw_cookie = ws.headers.get("Cookie") or ""
            parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
            for p in parts:
                if p.startswith("__session="):
                    token = p.split("=", 1)[1]
                    token_source = "websocket_session_cookie"
                    break
        except Exception:
            token = None

    # Log which cookie/token source authenticated the request
    if token:
        logger.debug(
            "auth.token_source",
            extra={
                "token_source": token_source,
                "has_token": bool(token),
                "token_length": len(token) if token else 0,
                "request_path": "websocket",
                "auth_method": "clerk",
            },
        )

    return token


def _claims_to_state(request_or_ws: Any, claims: dict[str, Any]) -> None:
    try:
        request_or_ws.state.jwt_payload = claims
    except Exception:
        pass
    # Clerk user id is in sub; also mirror to user_id
    uid = str(claims.get("sub") or claims.get("user_id") or "")
    if uid:
        try:
            request_or_ws.state.user_id = uid
        except Exception:
            pass
    # Email and roles (best-effort)
    email = claims.get("email") or claims.get("email_address")
    roles = claims.get("roles") or []
    try:
        request_or_ws.state.email = email
    except Exception:
        pass
    try:
        request_or_ws.state.roles = roles if isinstance(roles, list | tuple) else []
    except Exception:
        pass


def verify_clerk_token(token: str) -> dict[str, Any]:
    client, iss, aud = _jwks_client()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        options = {"require": ["exp", "iat", "sub"]}
        kwargs: dict[str, Any] = {}
        if iss:
            kwargs["issuer"] = iss
        if aud:
            kwargs["audience"] = aud
        claims = jwt_decode(
            token, signing_key.key, algorithms=["RS256"], options=options, **kwargs
        )
        return claims
    except Exception:
        raise _std_401()


async def require_user(request: Request) -> str:
    """FastAPI dependency that enforces a valid Clerk JWT.

    On success, attaches claims to ``request.state`` and returns the user id.
    """
    # Skip CORS preflight requests
    if request.method == "OPTIONS":
        return "anon"
    token = _extract_bearer_from_request(request)
    if not token:
        raise _std_401()
    claims = verify_clerk_token(token)
    _claims_to_state(request, claims)
    uid = str(claims.get("sub") or claims.get("user_id") or "")
    if not uid:
        raise _std_401()
    return uid


async def require_user_ws(ws: WebSocket) -> str:
    """WS handshake guard: verifies Clerk JWT and sets ws.state fields.

    Rejects with policy violation when token is missing/invalid.
    """
    token = _extract_bearer_from_ws(ws)
    if not token:
        try:
            await ws.close(code=1008, reason="unauthorized")
        finally:
            pass
        raise _std_401()
    try:
        claims = verify_clerk_token(token)
    except HTTPException:
        try:
            await ws.close(code=1008, reason="invalid_token")
        finally:
            pass
        raise
    _claims_to_state(ws, claims)
    uid = str(claims.get("sub") or claims.get("user_id") or "")
    if not uid:
        try:
            await ws.close(code=1008, reason="unauthorized")
        finally:
            pass
        raise _std_401()
    return uid


__all__ = ["require_user", "require_user_ws", "verify_clerk_token"]
