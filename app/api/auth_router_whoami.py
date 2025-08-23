from fastapi import APIRouter, Depends, Request, Response

router = APIRouter()

# Delegate to existing implementation in app.api.auth to keep logic centralized.
from .auth import whoami as _whoami_impl
from app.deps.user import get_current_user_id


@router.get("/whoami")
async def whoami(request: Request):
    return await _whoami_impl(request)


@router.get("/auth/finish")
@router.post("/auth/finish")
async def finish(request: Request, response: Response, user_id: str = Depends(get_current_user_id)):
    """Fixed auth finish endpoint - sets cookies and redirects."""
    from fastapi.responses import RedirectResponse
    from app.url_helpers import sanitize_redirect_path
    from app.cookies import set_auth_cookies
    from app.tokens import make_access, make_refresh
    from app.api.auth import _jwt_secret, _get_refresh_ttl_seconds
    from datetime import datetime, timedelta
    import time

    # Create tokens
    access_token = make_access({"user_id": user_id})
    refresh_token = make_refresh({"user_id": user_id})

    # Get TTLs
    from app.cookie_config import get_token_ttls
    access_ttl, refresh_ttl = get_token_ttls()

    # Set cookies
    set_auth_cookies(
        response,
        access=access_token,
        refresh=refresh_token,
        session_id=f"sess_{int(time.time())}_{user_id[:8]}",
        access_ttl=access_ttl,
        refresh_ttl=refresh_ttl,
        request=request,
    )

    # Redirect for GET, 204 for POST
    if request.method == "GET":
        next_path = sanitize_redirect_path(request.query_params.get("next"), "/")
        return RedirectResponse(url=next_path, status_code=302)
    else:
        return Response(status_code=204)
