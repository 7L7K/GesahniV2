from fastapi import APIRouter, Request, HTTPException
import inspect

from app.integrations.google.routes import legacy_oauth_callback

router = APIRouter()


@router.get("/google/oauth/callback")
async def compat_google_oauth_callback(request: Request):
    try:
        maybe = legacy_oauth_callback(request)
    except Exception:
        raise HTTPException(status_code=404)

    if inspect.isawaitable(maybe):
        return await maybe
    return maybe


