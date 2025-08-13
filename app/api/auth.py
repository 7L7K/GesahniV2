from __future__ import annotations

import os
import time
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response

from ..deps.user import get_current_user_id
from ..user_store import user_store


router = APIRouter(tags=["auth"], include_in_schema=False)


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


__all__ = ["router"]


