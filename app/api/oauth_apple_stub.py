import os
import secrets
import urllib.parse as up

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.auth_providers import apple_enabled
from app.cookies import set_oauth_state_cookie

router = APIRouter(tags=["Auth"], prefix="")

APPLE_AUTH_URL = "https://appleid.apple.com/auth/authorize"


def _make_state() -> str:
    return secrets.token_urlsafe(24)


def _make_nonce() -> str:
    return secrets.token_urlsafe(24)


@router.get("/v1/auth/apple/start", include_in_schema=False)
async def apple_start(request: Request):
    if not apple_enabled():
        # mirror current behavior if disabled
        raise HTTPException(status_code=404, detail="apple_oauth_disabled")

    state = _make_state()
    nonce = _make_nonce()

    resp = RedirectResponse(
        url="/v1/auth/apple/callback?state=" + up.quote(state) + "&code=fake-dev-code",
        status_code=302,
    )

    # 10 minutes; HttpOnly; Lax is fine here (navigational)
    set_oauth_state_cookie(resp, state, request=request, ttl=600)

    # In prod with real Apple credentials, build a real redirect
    if os.getenv("APPLE_CLIENT_ID") and os.getenv("APPLE_TEAM_ID"):
        client_id = os.getenv("APPLE_CLIENT_ID")
        redirect_uri = os.getenv(
            "APPLE_REDIRECT_URI",
            f"{os.getenv('APP_URL','http://localhost:8000')}/v1/auth/apple/callback",
        )
        scope = "name email"
        auth_params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "response_mode": "form_post",
            "scope": scope,
            "state": state,
            "nonce": nonce,
        }
        resp = RedirectResponse(
            url=APPLE_AUTH_URL + "?" + up.urlencode(auth_params), status_code=302
        )

    return resp


@router.get("/v1/auth/apple/callback", include_in_schema=False)
async def apple_callback(
    state: str | None = None, code: str | None = None, request: Request = None
):
    # Verify state cookie exists and matches
    cookie = request.cookies.get("oauth_state")
    if not state or not cookie or state != cookie:
        raise HTTPException(status_code=400, detail="oauth_state_mismatch")

    # Clear state cookie (best-effort) using centralized cookie facade
    from app.cookies import clear_oauth_state_cookies

    resp = Response(status_code=200, media_type="application/json")
    try:
        clear_oauth_state_cookies(resp, request=request, provider="oauth")
    except Exception:
        # Best-effort; if cookie clearing fails, continue to return response
        pass

    # In a real flow, you’d exchange code → id_token and verify nonce/aud/iss.
    # For stub, just acknowledge.
    resp.body = b'{"status":"ok","provider":"apple"}'
    return resp
