from __future__ import annotations

import os
import time
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm

from ..deps.user import get_current_user_id
from ..user_store import user_store


router = APIRouter(tags=["Auth"], include_in_schema=False)


def _jwt_secret() -> str:
    sec = os.getenv("JWT_SECRET")
    if not sec:
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    return sec


def _make_jwt(user_id: str, *, exp_seconds: int) -> str:
    now = int(time.time())
    payload = {"user_id": user_id, "iat": now, "exp": now + exp_seconds}
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


@router.post("/auth/login")
async def login(username: str, response: Response):
    # Smart minimal login: accept any non-empty username for dev; in prod plug real check
    if not username:
        raise HTTPException(status_code=400, detail="missing_username")
    # In a real app, validate password/OTP/etc. Here we mint a session for the username
    token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))  # 14 days
    jwt_token = _make_jwt(username, exp_seconds=token_lifetime)
    cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=token_lifetime,
        path="/",
    )
    await user_store.ensure_user(username)
    await user_store.increment_login(username)
    return {"status": "ok", "user_id": username}


@router.post("/auth/logout")
async def logout(response: Response, user_id: str = Depends(get_current_user_id)):
    response.delete_cookie("access_token", path="/")
    return {"status": "ok"}


@router.post("/auth/refresh")
async def refresh(response: Response, user_id: str = Depends(get_current_user_id)):
    if user_id == "anon":
        raise HTTPException(status_code=401, detail="not_logged_in")
    token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))
    jwt_token = _make_jwt(user_id, exp_seconds=token_lifetime)
    cookie_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes", "on"}
    cookie_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        secure=cookie_secure,
        samesite=cookie_samesite,
        max_age=token_lifetime,
        path="/",
    )
    return {"status": "ok", "user_id": user_id}


# OAuth2 Password flow endpoint for Swagger "Authorize" in dev
@router.post("/auth/token", include_in_schema=True)
async def issue_token(form_data: OAuth2PasswordRequestForm = Depends()):
    # Gate for production environments
    if os.getenv("DISABLE_DEV_TOKEN", "0").lower() in {"1", "true", "yes", "on"}:
        raise HTTPException(status_code=403, detail="disabled")
    username = (form_data.username or "dev").strip() or "dev"
    token_lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))
    now = int(time.time())
    scopes = form_data.scopes or []
    payload = {
        "user_id": username,
        "sub": username,
        "iat": now,
        "exp": now + token_lifetime,
    }
    if scopes:
        payload["scope"] = " ".join(sorted(set(scopes)))
    token = jwt.encode(payload, _jwt_secret(), algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}


@router.get("/auth/examples")
async def token_examples():
    """Return sanitized JWT examples and common scope sets.

    These are not valid tokens; use /v1/auth/token to mint a real dev token.
    """
    return {
        "samples": {
            "header": {"alg": "HS256", "typ": "JWT"},
            "payload": {
                "user_id": "dev",
                "sub": "dev",
                "exp": 1714764000,
                "scope": "admin:write",
            },
            "jwt_example": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.ey...<redacted>...",
        },
        "scopes": [
            "care:resident",
            "care:caregiver",
            "music:control",
            "admin:write",
        ],
        "notes": "Use /v1/auth/token with 'scopes' to mint a real token in dev.",
    }


__all__ = ["router"]


