"""
Settings API endpoints.

Provides basic settings and configuration information for the frontend.
"""

import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/settings")


@router.get("/")
async def get_settings(request: Request) -> JSONResponse:
    """
    Get basic settings and configuration information.

    This endpoint provides frontend configuration and status information
    that the settings page might need.
    """
    try:
        # Basic settings/configuration that might be useful for the frontend
        settings = {
            "features": {
                "google_oauth": bool(os.getenv("GOOGLE_CLIENT_ID")),
                "spotify_oauth": bool(os.getenv("SPOTIFY_CLIENT_ID")),
                "home_assistant": bool(os.getenv("HOME_ASSISTANT_URL")),
                "llama": bool(os.getenv("OLLAMA_URL")),
                "openai": bool(os.getenv("OPENAI_API_KEY")),
            },
            "environment": {
                "dev_mode": os.getenv("DEV_MODE", "0") == "1",
                "debug": os.getenv("DEBUG", "false").lower() == "true",
            },
            "version": os.getenv("VERSION", "unknown"),
        }

        return JSONResponse(content=settings, status_code=200)

    except Exception as e:
        # Log the error but return a basic response
        import logging
        logger = logging.getLogger(__name__)
        logger.exception("Error fetching settings: %s", e)

        # Return minimal settings on error
        return JSONResponse(
            content={
                "features": {
                    "google_oauth": False,
                    "spotify_oauth": False,
                    "home_assistant": False,
                    "llama": False,
                    "openai": False,
                },
                "environment": {
                    "dev_mode": False,
                    "debug": False,
                },
                "version": "unknown",
            },
            status_code=200
        )
