"""
Configuration self-check endpoint for operational visibility.
Provides read-only summary of environment and feature configuration.
"""

import os

from fastapi import APIRouter

router = APIRouter(prefix="/v1/admin", tags=["Admin"])


def _truthy(v):
    """Check if a string value represents truthy."""
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


@router.get("/config-check")
def config_check():
    """
    Get a redacted configuration summary for operational visibility.

    Returns environment and feature flags without exposing sensitive values.
    Useful for debugging configuration issues and verifying deployments.
    """
    env = (os.getenv("ENV") or "dev").strip().lower()

    return {
        "env": env,
        "ci": _truthy(os.getenv("CI")),
        "dev_mode": _truthy(os.getenv("DEV_MODE")),
        "features": {
            "spotify": _truthy(os.getenv("SPOTIFY_ENABLED")),
            "apple_oauth": _truthy(os.getenv("APPLE_OAUTH_ENABLED")),
            "device_auth": _truthy(os.getenv("DEVICE_AUTH_ENABLED")),
            "preflight": _truthy(os.getenv("PREFLIGHT_ENABLED", "1")),
            "llama": _truthy(os.getenv("LLAMA_ENABLED")),
            "home_assistant": _truthy(os.getenv("HOME_ASSISTANT_ENABLED")),
        },
        "security": {
            "jwt_len": len(os.getenv("JWT_SECRET", "")),
            "cookies_secure": _truthy(os.getenv("COOKIES_SECURE", "1")),
            "cookies_samesite": os.getenv("COOKIES_SAMESITE", "strict").lower(),
            "rate_limit_enabled": _truthy(os.getenv("RATE_LIMIT_ENABLED", "1")),
            "req_id_enabled": _truthy(os.getenv("REQ_ID_ENABLED", "1")),
        },
        "middleware": {
            "cors_enabled": _truthy(os.getenv("CORS_ENABLED", "1")),
            "legacy_error_mw": _truthy(os.getenv("LEGACY_ERROR_MW")),
            "deterministic_router": _truthy(os.getenv("DETERMINISTIC_ROUTER")),
        },
        "external": {
            "openai_available": bool(os.getenv("OPENAI_API_KEY")),
            "home_assistant_token": bool(os.getenv("HOME_ASSISTANT_TOKEN")),
            "spotify_client_id": bool(os.getenv("SPOTIFY_CLIENT_ID")),
        },
    }
