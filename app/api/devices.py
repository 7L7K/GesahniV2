from __future__ import annotations

import os
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.deps.user import get_current_user_id
from app.device_tokens import (
    consume_pair_code,
    revoke_device_token,
    store_pair_code,
    upsert_device_token,
)

router = APIRouter(tags=["Admin"])


def _jwt_secret() -> str:
    sec = os.getenv("JWT_SECRET")
    if not sec:
        raise HTTPException(status_code=500, detail="missing_jwt_secret")
    return sec


def _now() -> int:
    return int(time.time())


@router.post("/devices/pair/start")
async def pair_start(
    request: Request, user_id: str = Depends(get_current_user_id)
) -> dict[str, Any]:
    if not user_id or user_id == "anon":
        from ..http_errors import unauthorized

        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )
    label = (request.headers.get("X-Device-Label") or "tv").strip()
    code = secrets.token_hex(3).lower()
    ttl = int(os.getenv("DEVICE_PAIR_CODE_TTL_S", "300"))
    await store_pair_code(code, user_id, label, ttl_seconds=ttl)
    return {"code": code, "expires_in": ttl}


@router.post("/devices/pair/complete")
async def pair_complete(body: dict[str, Any]) -> dict[str, Any]:
    code = str(body.get("code") or "").strip().lower()
    if not code:
        raise HTTPException(status_code=400, detail="missing_code")
    info = await consume_pair_code(code)
    if not info:
        raise HTTPException(status_code=400, detail="invalid_or_expired_code")
    owner_id, label = info
    # Mint a resident-scoped device token
    now = _now()
    ttl = int(os.getenv("DEVICE_TOKEN_TTL_S", "2592000"))  # default 30 days
    now + ttl
    jti = secrets.token_urlsafe(16)
    # Use tokens.py facade instead of direct JWT encoding
    from ..tokens import make_access

    token = make_access(
        {"user_id": owner_id, "jti": jti, "device": label or "tv"}, ttl_s=ttl
    )
    # Persist token id for revocation and metadata lookup
    await upsert_device_token(jti, owner_id, label or "tv", ttl)
    return {"access_token": token, "token_type": "bearer", "expires_in": ttl}


@router.post("/devices/{device_id}/revoke")
async def device_revoke(
    device_id: str, request: Request, user_id: str = Depends(get_current_user_id)
) -> dict[str, str]:
    # Revoke the current device token for this owner+device by deleting the stored token id
    # Clients should rotate token immediately after this call
    jti = request.headers.get("X-Device-Token-ID") or ""
    # Best-effort: allow body to pass token id too
    try:
        body = await request.json()
        jti = body.get("jti") or jti
    except Exception:
        pass
    if not jti:
        # In absence of provided jti, revocation is best-effort (no-op)
        return {"status": "ok"}
    await revoke_device_token(str(jti))
    return {"status": "ok"}
