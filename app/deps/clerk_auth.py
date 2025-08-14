from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Request, WebSocket
import jwt
from jwt import PyJWKClient


def _std_401() -> HTTPException:
    return HTTPException(status_code=401, detail="Unauthorized")


def _std_500(msg: str) -> HTTPException:
    return HTTPException(status_code=500, detail=msg)


def _read_env(name: str) -> str:
    return os.getenv(name, "").strip()


def _derive_issuer_and_jwks() -> Tuple[str, str]:
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
def _jwks_client() -> Tuple[PyJWKClient, str, Optional[str]]:
    iss, jwks_url = _derive_issuer_and_jwks()
    if not jwks_url:
        raise _std_500("clerk_not_configured")
    # Audience is optional; when provided we enforce it
    aud = _read_env("CLERK_AUDIENCE") or _read_env("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY")
    client = PyJWKClient(jwks_url)
    return client, iss, (aud or None)


def _extract_bearer_from_request(request: Request) -> Optional[str]:
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth.split(" ", 1)[1]
    # Clerk SSR cookie (when proxied) — best-effort; JWT is not stored in our own cookies
    cookie = request.cookies.get("__session") or request.cookies.get("session")
    if cookie and cookie.count(".") >= 2:
        return cookie
    return None


def _extract_bearer_from_ws(ws: WebSocket) -> Optional[str]:
    auth = ws.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        return auth.split(" ", 1)[1]
    try:
        tok = ws.query_params.get("token") or ws.query_params.get("access_token") or ws.query_params.get("__session")
        if tok:
            return tok
    except Exception:
        pass
    try:
        raw_cookie = ws.headers.get("Cookie") or ""
        parts = [p.strip() for p in raw_cookie.split(";") if p.strip()]
        for p in parts:
            if p.startswith("__session="):
                return p.split("=", 1)[1]
    except Exception:
        pass
    return None


def _claims_to_state(request_or_ws: Any, claims: Dict[str, Any]) -> None:
    try:
        setattr(request_or_ws.state, "jwt_payload", claims)
    except Exception:
        pass
    # Clerk user id is in sub; also mirror to user_id
    uid = str(claims.get("sub") or claims.get("user_id") or "")
    if uid:
        try:
            setattr(request_or_ws.state, "user_id", uid)
        except Exception:
            pass
    # Email and roles (best-effort)
    email = claims.get("email") or claims.get("email_address")
    roles = claims.get("roles") or []
    try:
        setattr(request_or_ws.state, "email", email)
    except Exception:
        pass
    try:
        setattr(request_or_ws.state, "roles", roles if isinstance(roles, (list, tuple)) else [])
    except Exception:
        pass


def verify_clerk_token(token: str) -> Dict[str, Any]:
    client, iss, aud = _jwks_client()
    try:
        signing_key = client.get_signing_key_from_jwt(token)
        options = {"require": ["exp", "iat", "sub"]}
        kwargs: Dict[str, Any] = {}
        if iss:
            kwargs["issuer"] = iss
        if aud:
            kwargs["audience"] = aud
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"], options=options, **kwargs)
        return claims
    except Exception:
        raise _std_401()


async def require_user(request: Request) -> str:
    """FastAPI dependency that enforces a valid Clerk JWT.

    On success, attaches claims to ``request.state`` and returns the user id.
    """
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


