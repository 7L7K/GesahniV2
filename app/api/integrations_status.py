import logging
import os
import time

from fastapi import APIRouter, Request

from app.integrations.spotify.client import SpotifyClient
from app.env_helpers import env_flag

from ..auth_store_tokens import get_token
from ..deps.user import resolve_user_id

logger = logging.getLogger(__name__)
router = APIRouter()


def log_integrations_status(
    operation: str, user_id: str = None, details: dict = None, level: str = "info"
):
    """Enhanced integrations status logging."""
    details = details or {}
    log_data = {
        "operation": operation,
        "component": "integrations_status",
        "timestamp": time.time(),
        **details,
    }
    if user_id:
        log_data["user_id"] = user_id

    if level == "debug":
        logger.debug(f"🔗 INTEGRATIONS {operation.upper()}", extra={"meta": log_data})
    elif level == "warning":
        logger.warning(f"🔗 INTEGRATIONS {operation.upper()}", extra={"meta": log_data})
    elif level == "error":
        logger.error(f"🔗 INTEGRATIONS {operation.upper()}", extra={"meta": log_data})
    else:
        logger.info(f"🔗 INTEGRATIONS {operation.upper()}", extra={"meta": log_data})


@router.get("/integrations/status")
async def integrations_status(request: Request):
    log_integrations_status(
        "status_request_start",
        None,
        {"message": "Starting integrations status request"},
    )

    spotify_result = {"connected": False}

    # Check Spotify enabled status
    spotify_flag = env_flag(
        "GSNH_ENABLE_SPOTIFY",
        default=False,
        legacy=("SPOTIFY_ENABLED",),
    )
    music_flag = env_flag("GSNH_ENABLE_MUSIC", default=True)
    spotify_enabled_env = os.getenv("GSNH_ENABLE_SPOTIFY") or os.getenv("SPOTIFY_ENABLED") or ""
    log_integrations_status(
        "spotify_enabled_check",
        None,
        {
            "message": "Checking Spotify enabled status",
            "spotify_enabled_env": spotify_enabled_env,
            "is_enabled": spotify_flag and music_flag,
        },
    )

    # Short-circuit if Spotify integration is disabled via env
    if not (spotify_flag and music_flag):
        spotify_result = {"connected": False, "reason": "disabled"}
        log_integrations_status(
            "spotify_disabled",
            None,
            {
                "message": "Spotify integration disabled via environment",
                "spotify_result": spotify_result,
            },
        )
    else:
        try:
            # Use resolve_user_id for internal calls to avoid raising in non-FastAPI contexts
            log_integrations_status(
                "user_resolution_start", None, {"message": "Starting user resolution"}
            )

            current_user = await resolve_user_id(request=request)
            log_integrations_status(
                "user_resolution_result",
                current_user,
                {
                    "message": "User resolution completed",
                    "user_resolved": current_user is not None,
                    "is_anon": current_user == "anon",
                },
            )

            if current_user and current_user != "anon":
                log_integrations_status(
                    "spotify_client_creation",
                    current_user,
                    {"message": "Creating Spotify client for user"},
                )

                client = SpotifyClient(current_user)
                try:
                    log_integrations_status(
                        "spotify_profile_check",
                        current_user,
                        {"message": "Testing Spotify API connection via profile check"},
                    )

                    # Actually test the Spotify API connection instead of just checking token existence
                    profile = await client.get_user_profile()

                    if profile is not None:
                        spotify_result = {"connected": True}
                        log_integrations_status(
                            "spotify_connected",
                            current_user,
                            {
                                "message": "Spotify connection successful",
                                "profile_keys": (
                                    list(profile.keys())
                                    if isinstance(profile, dict)
                                    else None
                                ),
                            },
                        )
                    else:
                        spotify_result = {
                            "connected": False,
                            "reason": "profile_check_failed",
                        }
                        log_integrations_status(
                            "spotify_profile_failed",
                            current_user,
                            {
                                "message": "Profile check returned None",
                                "spotify_result": spotify_result,
                                "level": "warning",
                            },
                            level="warning",
                        )
                except RuntimeError as e:
                    # Sanitize internal errors
                    msg = str(e)
                    if "attempted relative import" in msg:
                        msg = "module_import_error"
                    spotify_result = {"connected": False, "reason": msg}
                    log_integrations_status(
                        "spotify_runtime_error",
                        current_user,
                        {
                            "message": "Runtime error during Spotify connection test",
                            "error": str(e),
                            "sanitized_message": msg,
                            "spotify_result": spotify_result,
                            "level": "warning",
                        },
                        level="warning",
                    )
            else:
                spotify_result = {
                    "connected": False,
                    "reason": "user_not_authenticated",
                }
                log_integrations_status(
                    "spotify_user_not_auth",
                    current_user,
                    {
                        "message": "User not authenticated for Spotify check",
                        "spotify_result": spotify_result,
                    },
                )
        except Exception as e:
            # Don't leak internal stack traces to UI
            msg = str(e)
            original_error = msg

            # Check for database connectivity issues
            if "connection" in msg.lower() or "psycopg" in str(type(e)).lower():
                msg = "database_connection_error"
                log_integrations_status(
                    "spotify_database_error",
                    current_user,
                    {
                        "message": "Database connectivity error during Spotify status check",
                        "error": original_error,
                        "sanitized_message": msg,
                        "spotify_result": {"connected": False, "reason": msg},
                        "level": "error",
                        "cause": "PostgreSQL database not accessible",
                        "solution": "Start PostgreSQL service",
                    },
                    level="error",
                )
            elif "attempted relative import" in msg:
                msg = "module_import_error"
                log_integrations_status(
                    "spotify_import_error",
                    current_user,
                    {
                        "message": "Import error during Spotify status check",
                        "error": original_error,
                        "sanitized_message": msg,
                        "spotify_result": {"connected": False, "reason": msg},
                        "level": "error",
                    },
                    level="error",
                )
            else:
                log_integrations_status(
                    "spotify_unexpected_error",
                    current_user,
                    {
                        "message": "Unexpected error during Spotify status check",
                        "error": original_error,
                        "sanitized_message": msg,
                        "spotify_result": {"connected": False, "reason": msg},
                        "level": "error",
                    },
                    level="error",
                )

            spotify_result = {"connected": False, "reason": msg}

    # Compute Google provider health by inspecting tokens
    google_result = {"status": "not_connected"}
    try:
        current_user = resolve_user_id(request=request)
        if current_user and current_user != "anon":
            t = await get_token(current_user, "google")
            if not t:
                google_result = {"status": "not_connected"}
            else:
                # Simple truth: if is_valid false -> not_connected
                if not t.is_valid:
                    google_result = {"status": "not_connected", "reason": "invalid"}
                else:
                    # Degraded if expired and refresh would fail (we attempt probe)
                    now = int(time.time())
                    if (t.expires_at - now) < 300:
                        google_result = {
                            "status": "degraded",
                            "reason": "refresh_failed",
                        }
                    else:
                        google_result = {"status": "connected"}
    except Exception as e:
        google_result = {"status": "not_connected", "reason": str(e)}

    return {
        "spotify": spotify_result,
        "google": google_result,
        "home_assistant": {"connected": False},
    }
