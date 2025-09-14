import inspect
import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response

from app.integrations.google.routes import legacy_oauth_callback

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/google/oauth/callback", deprecated=True)
async def compat_google_oauth_callback(request: Request):
    # Check if legacy Google OAuth is enabled
    legacy_enabled = os.getenv("GSN_ENABLE_LEGACY_GOOGLE", "0").strip()
    if legacy_enabled != "1":
        logger.info(
            "google_oauth.legacy_disabled",
            extra={
                "req_id": getattr(request.state, "req_id", "-"),
                "path": str(request.url.path),
                "component": "google_oauth",
            },
        )
        raise HTTPException(
            status_code=410, detail="Legacy Google OAuth endpoint disabled"
        )

    try:
        maybe = legacy_oauth_callback(request)
    except Exception:
        raise HTTPException(status_code=404)

    if inspect.isawaitable(maybe):
        response = await maybe
    else:
        response = maybe

    # Log legacy usage for monitoring
    logger.info(
        "google_oauth.legacy_used",
        extra={
            "req_id": getattr(request.state, "req_id", "-"),
            "path": str(request.url.path),
            "legacy": True,
            "component": "google_oauth",
        },
    )

    # Add deprecation headers if it's a Response object
    if isinstance(response, Response):
        response.headers["Sunset"] = "Mon, 01 Sep 2025 00:00:00 GMT"
        response.headers["Link"] = (
            '<https://docs.example.com/deprecated/google-oauth>; rel="sunset"'
        )
        response.headers["Deprecation"] = "true"

    return response
