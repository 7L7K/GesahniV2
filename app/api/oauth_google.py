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


# POST shim: some clients POST to the callback URL; respond with 303 to canonical GET
@router.post("/v1/auth/google/callback")
async def legacy_google_callback_post(request: Request):
    """Return a 303 See Other redirect to the canonical GET callback endpoint."""
    # Preserve query string if any
    qs = request.scope.get("query_string", b"").decode()
    target = "/v1/auth/google/callback" + (f"?{qs}" if qs else "")
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url=target, status_code=303)

__all__ = ["router"]
