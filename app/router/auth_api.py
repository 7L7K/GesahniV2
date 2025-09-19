"""Legacy auth router - not currently used.

Legacy routes are now handled directly in app.api.auth with include_in_schema=False.
This router is kept for potential future use if redirects are needed.
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

router = APIRouter()


@router.get("/auth/finish")
async def auth_finish_get(request: Request) -> Response:
    """OAuth finisher endpoint that sets auth cookies after OAuth callback.

    This endpoint is called after OAuth callback processing to set the final
    auth cookies and redirect to the application.
    """
    from app.auth.cookie_utils import rotate_session_id
    from app.web.cookies import set_auth_cookies
    from app.tokens import make_access, make_refresh
    from app.redirect_utils import get_safe_redirect_target
    from app.cookie_config import get_token_ttls

    # Get user_id from query params first, then request state
    user_id = request.query_params.get('user_id')

    if not user_id:
        user_id = getattr(request.state, 'user_id', None)

    if not user_id:
        user_id = getattr(request.state, 'uid', None)

    if not user_id:
        user_id = 'anon'

    # Mint tokens for the authenticated user
    access_token = make_access({"user_id": user_id})
    refresh_token = make_refresh({"user_id": user_id})

    # Get token TTLs
    access_ttl, refresh_ttl = get_token_ttls()

    # Create session ID from access token
    try:
        from app.security import jwt_decode
        access_payload = jwt_decode(access_token, options={"verify_signature": False})
        session_id = rotate_session_id(
            response := RedirectResponse(url="/", status_code=302),
            request,
            user_id=user_id,
            access_token=access_token,
            access_payload=access_payload,
        )
    except Exception:
        # Fallback to new session ID if token decode fails
        from app.session_store import new_session_id
        session_id = new_session_id()
        response = RedirectResponse(url="/", status_code=302)

    # Set auth cookies using centralized cookie helpers
    set_auth_cookies(
        response,
        access=access_token,
        refresh=refresh_token,
        session_id=session_id,
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=request,
    )

    # Determine redirect target (gs_next cookie priority)
    frontend_url = get_safe_redirect_target(request, fallback="/")
    response.headers["Location"] = frontend_url

    return response
