from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..deps.user import get_current_user_id

router = APIRouter(
    prefix="/spotify",
    tags=["Music"],
)


@router.get("/token-for-sdk")
async def token_for_sdk(request: Request, user_id: str = Depends(get_current_user_id)):
    try:
        from ..auth_store_tokens import get_valid_token_with_auto_refresh

        token = await get_valid_token_with_auto_refresh(user_id, "spotify", False)
        if token and token.is_expired(60):
            token = await get_valid_token_with_auto_refresh(user_id, "spotify", True)

        if not token:
            raise RuntimeError("not_connected")

        return {
            "ok": True,
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_at": token.expires_at,
            "scopes": token.scopes.split() if token.scopes else [],
            "provider_sub": token.provider_sub,
        }
    except RuntimeError as exc:
        detail = str(exc)
        if detail in {"not_connected", "needs_reauth"}:
            from ..http_errors import unauthorized

            msg = (
                "spotify not connected"
                if detail == "not_connected"
                else "spotify needs reauth"
            )
            hint = (
                "connect Spotify account"
                if detail == "not_connected"
                else "reauthorize Spotify access"
            )
            raise unauthorized(code=detail, message=msg, hint=hint)
        raise
