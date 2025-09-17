from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from app.auth.jwt_utils import _decode_any
from app.auth.models import WhoAmIOut
from app.auth_debug import log_incoming_cookies

router = APIRouter(tags=["Auth"])  # expose in OpenAPI for docs/tests
logger = logging.getLogger(__name__)


@router.get("/debug/cookies")
def debug_cookies(request: Request) -> dict[str, dict[str, str]]:
    """Echo cookie presence for debugging (values not exposed).

    Returns a mapping of cookie names to "present"/empty string so callers can
    determine whether the browser attached cookies on this request.
    """
    try:
        cookies = {
            k: ("present" if (v is not None and v != "") else "")
            for k, v in request.cookies.items()
        }
    except AttributeError as e:
        logger.warning(f"Request object missing cookies attribute: {e}")
        cookies = {}
    except (TypeError, ValueError) as e:
        logger.warning(f"Invalid cookies data structure: {e}")
        cookies = {}
    except Exception as e:
        logger.error(
            f"Unexpected error accessing cookies for debug: {type(e).__name__}: {e}"
        )
        cookies = {}
    return {"cookies": cookies}


@router.get("/debug/auth-state")
def debug_auth_state(request: Request) -> dict[str, Any]:
    """Debug auth state - shows cookies received and token validation status.

    Returns comprehensive auth debugging info including:
    - All cookies received by name
    - Whether access/refresh/session cookies are present and valid
    - Current authentication status
    """
    try:
        # Import cookie readers
        from app.cookies import (
            read_access_cookie,
            read_refresh_cookie,
            read_session_cookie,
        )

        # Read tokens from cookies
        access = read_access_cookie(request)
        refresh = read_refresh_cookie(request)
        session = read_session_cookie(request)

        # Check if tokens are valid (basic decode check)
        access_valid = False
        refresh_valid = False
        session_valid = bool(session)  # Session is just an opaque string

        access_valid = bool(_decode_any(access)) if access else False
        refresh_valid = bool(_decode_any(refresh)) if refresh else False

        return {
            "cookies_seen": list(request.cookies.keys()),
            "has_access": bool(access),
            "has_refresh": bool(refresh),
            "has_session": bool(session),
            "access_valid": access_valid,
            "refresh_valid": refresh_valid,
            "session_valid": session_valid,
            "cookie_count": len(request.cookies),
        }
    except Exception as e:
        logger.error(f"Failed to process auth state for debug endpoint: {e}")
        return {
            "error": str(e),
            "cookies_seen": (
                list(request.cookies.keys()) if hasattr(request, "cookies") else []
            ),
            "has_access": False,
            "has_refresh": False,
            "has_session": False,
        }


@router.get("/whoami", include_in_schema=False, response_model=WhoAmIOut)
async def whoami(request: Request, response: Response) -> JSONResponse:
    """Public whoami endpoint with lazy refresh capability."""
    from app.auth.service import AuthService

    # Debug logging if enabled
    try:
        if os.getenv("AUTH_DEBUG") == "1":
            log_incoming_cookies(request, route="/v1/whoami")
    except Exception:
        pass

    # Get authentication state with lazy refresh
    try:
        result = await AuthService.whoami_with_lazy_refresh(request, response)
        return result
    except Exception as e:
        # Handle authentication errors gracefully
        from fastapi import HTTPException

        if isinstance(e, HTTPException):
            raise e

        # Return unauthenticated state on error
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {
                "is_authenticated": False,
                "session_ready": False,
                "user": {"id": None, "email": None},
                "source": "error",
                "version": 1,
            },
            status_code=200,
        )
