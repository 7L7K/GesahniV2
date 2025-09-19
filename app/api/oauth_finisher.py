"""OAuth finisher endpoint for completing authentication flows.

This module provides the OAuth finisher that sets authentication cookies
and redirects to the appropriate frontend URL after OAuth callbacks.
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from ..auth.cookie_utils import rotate_session_id
from ..web.cookies import set_auth_cookies
from ..tokens import make_access, make_refresh
from ..redirect_utils import get_safe_redirect_target

router = APIRouter()


@router.get("/finish")
async def oauth_finish(request: Request, response: Response, user_id: str | None = None):
    """Complete OAuth flow by setting auth cookies and redirecting.

    This endpoint:
    1. Extracts the user_id from query params or request state
    2. Mints access and refresh tokens
    3. Sets HttpOnly auth cookies
    4. Redirects to the frontend with appropriate next URL

    Expected user_id should be passed as query parameter from OAuth callback.
    """
    # Get user_id from query params first, then request state
    if not user_id:
        user_id = request.query_params.get('user_id')

    if not user_id:
        user_id = getattr(request.state, 'user_id', None)

    if not user_id:
        user_id = getattr(request.state, 'uid', None)

    if not user_id:
        user_id = 'anon'

    # Create user authentication session first
    from app.sessions_store import sessions_store
    auth_session_result = await sessions_store.create_session(user_id, device_name="OAuth")
    auth_session_id = auth_session_result["sid"]

    # Get the current session version
    sess_ver = await sessions_store.get_session_version(auth_session_id)

    # Mint tokens for the authenticated user
    access_token = make_access({"user_id": user_id, "sid": auth_session_id, "sess_ver": sess_ver})
    refresh_token = make_refresh({"user_id": user_id, "sid": auth_session_id, "sess_ver": sess_ver})

    # Create session ID from access token
    try:
        from ..security import jwt_decode
        access_payload = jwt_decode(access_token, options={"verify_signature": False})
        at_jti = access_payload.get("jti")
        exp = access_payload.get("exp", 0)
        session_id = rotate_session_id(response, request, user_id=user_id, access_token=access_token, access_payload=access_payload)
    except Exception:
        # Fallback to new session ID if token decode fails
        from ..session_store import new_session_id
        session_id = new_session_id()

    # Set auth cookies using centralized cookie helpers
    set_auth_cookies(
        response,
        access=access_token,
        refresh=refresh_token,
        session_id=session_id,
        request=request,
    )

    # Determine redirect target (gs_next cookie priority)
    frontend_url = get_safe_redirect_target(request, fallback="/")

    # Return redirect response
    return RedirectResponse(url=frontend_url, status_code=302)
