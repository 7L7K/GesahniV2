from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form

from app.auth.models import TokenExamplesOut, TokenOut
from app.cookie_config import get_token_ttls
from app.http_errors import http_error
from app.tokens import make_access

router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests


@router.post("/token", response_model=TokenOut)
async def dev_token(
    username: str = Form(None),
    password: str = Form(None),
    scope: str = Form(""),
):
    import os as _os

    if (_os.getenv("DISABLE_DEV_TOKEN") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise http_error(
            code="ERR_DEV_TOKEN_DISABLED", message="dev token disabled", status=403
        )

    sec = _os.getenv("JWT_SECRET")
    if not sec or not str(sec).strip():
        raise http_error(
            code="ERR_MISSING_JWT_SECRET", message="JWT secret is missing", status=500
        )
    low = sec.strip().lower()
    if (
        len(sec) < 16
        or low.startswith("change")
        or low in {"default", "placeholder", "secret", "key"}
    ):
        raise http_error(
            code="ERR_INSECURE_JWT_SECRET", message="JWT secret is insecure", status=500
        )

    if not username:
        raise http_error(
            code="ERR_MISSING_USERNAME", message="Username is required", status=400
        )

    try:
        access_ttl, _ = get_token_ttls()
        payload: dict[str, Any] = {"user_id": username}
        if scope:
            payload["scope"] = scope
        token = make_access(payload, ttl_s=access_ttl)
    except Exception as e:
        raise http_error(
            code="ERR_TOKEN_ISSUE_FAILED", message="Failed to issue token", status=500
        ) from e

    return {"access_token": token, "token_type": "bearer"}


@router.get("/examples", response_model=TokenExamplesOut)
async def token_examples():
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
