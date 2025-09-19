from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["auth"], include_in_schema=False)


@router.get("/v1/auth/google/callback")
async def legacy_google_callback(request: Request):
    """Legacy compatibility endpoint for /v1/auth/google/callback.

    Performs OAuth token exchange and sets auth cookies, then redirects.
    Cookie names use the short 'g_' provider prefix consistent with tests.
    """
    from app.web.cookies import clear_oauth_state_cookies
    from fastapi.responses import RedirectResponse
    import os

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    # If no code/state, just redirect to home
    if not code or not state:
        resp = RedirectResponse(url="/", status_code=302)
        try:
            clear_oauth_state_cookies(resp, provider="g")
        except Exception:
            pass
        return resp

    try:
        # Import OAuth processing functions
        from app.integrations.google.oauth import exchange_code
        from app.api.google_oauth import _mint_cookie_redirect

        # Exchange the code for tokens
        creds = exchange_code(code, state)

        # Create user ID from OAuth response
        user_id = f"google_{creds.token[:16]}"  # Simple user ID from token

        # Mint cookies and redirect
        return _mint_cookie_redirect(request, "/", user_id=user_id)

    except Exception as e:
        # On OAuth failure, clear state and redirect to finisher
        resp = RedirectResponse(url="/auth/finish", status_code=302)
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
