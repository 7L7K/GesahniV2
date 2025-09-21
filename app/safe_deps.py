"""Safe dependency resolvers that degrade gracefully instead of throwing 500s."""

from typing import Any

from fastapi import Request

import app.deps.user as user


class NoAuthError(Exception):
    """Raised when authentication cannot be determined safely."""
    pass


async def get_current_user_id_safe(request: Request) -> str | None:
    """Safely resolve current user ID, returning None on any error.

    This prevents 500 errors from bubbling up when the user resolver has issues.
    Instead, routes can degrade gracefully by treating None as "not authorized".
    """
    try:
        # Call the existing async dependency
        result = await user.get_current_user_id(request=request)
        return result
    except Exception as e:
        # Log the error for debugging but don't let it bubble up
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "safe_resolver.exception_caught",
            extra={
                "meta": {
                    "resolver": "get_current_user_id_safe",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "action": "returning_none",
                    "reason": "prevent_500_error",
                    "timestamp": __import__('time').time()
                }
            }
        )
        # If this throws during a valid app session, DO NOT 500 the endpoint.
        # Return None so the route can degrade gracefully.
        return None
