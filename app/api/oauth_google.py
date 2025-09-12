from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["auth"], include_in_schema=False)


@router.get("/v1/auth/google/callback")
async def legacy_google_callback(request: Request):
    """Legacy compatibility endpoint for /v1/auth/google/callback.

    Returns a 303 redirect and clears OAuth state cookies set during login.
    Cookie names use the short 'g_' provider prefix consistent with tests.
    """
    from app.web.cookies import clear_oauth_state_cookies

    resp = RedirectResponse(url="/", status_code=303)
    try:
        clear_oauth_state_cookies(resp, provider="g")
    except Exception:
        pass
    return resp

__all__ = ["router"]
