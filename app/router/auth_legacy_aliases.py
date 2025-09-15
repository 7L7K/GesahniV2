"""Legacy auth route aliases with tracking.

This router provides backward compatibility for clients still using the old
/v1/* auth endpoints by redirecting them to the canonical /v1/auth/* routes
with deprecation headers, logging, and metrics tracking.
"""

from fastapi import APIRouter, Request, Response

from ..api.auth import login_v1, logout, refresh
from .legacy_alias import LegacyAlias

router = APIRouter(tags=["Auth Legacy"])

# Legacy route: POST /v1/login → POST /v1/auth/login
legacy_login = LegacyAlias("/login", "/v1/auth/login", "POST", login_v1)


@router.post(
    "/login",
    deprecated=True,
    include_in_schema=True,
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {
                            "access_token": "jwt_token",
                            "refresh_token": "refresh_jwt",
                        }
                    }
                }
            }
        }
    },
)
async def legacy_login_handler(request: Request, response: Response):
    """Legacy login endpoint - deprecated.

    This endpoint is deprecated and will be removed after 2025-12-31.
    Please use POST /v1/auth/login instead.

    For backward compatibility, this endpoint redirects to the canonical
    auth route with deprecation tracking.
    """
    return await legacy_login(request, response)


# Note: /register and /whoami are provided by the canonical auth router
# so we don't need legacy aliases for them


# Legacy route: POST /v1/logout → POST /v1/auth/logout
legacy_logout = LegacyAlias("/logout", "/v1/auth/logout", "POST", logout)


@router.post(
    "/logout",
    deprecated=True,
    include_in_schema=True,
    responses={
        200: {
            "content": {
                "application/json": {"schema": {"example": {"message": "logged out"}}}
            }
        }
    },
)
async def legacy_logout_handler(request: Request, response: Response):
    """Legacy logout endpoint - deprecated.

    This endpoint is deprecated and will be removed after 2025-12-31.
    Please use POST /v1/auth/logout instead.

    For backward compatibility, this endpoint redirects to the canonical
    auth route with deprecation tracking.
    """
    return await legacy_logout(request, response)


# Legacy route: POST /v1/refresh → POST /v1/auth/refresh
legacy_refresh = LegacyAlias("/refresh", "/v1/auth/refresh", "POST", refresh)


@router.post(
    "/refresh",
    deprecated=True,
    include_in_schema=True,
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {
                        "example": {
                            "access_token": "jwt_token",
                            "refresh_token": "refresh_jwt",
                        }
                    }
                }
            }
        }
    },
)
async def legacy_refresh_handler(request: Request, response: Response):
    """Legacy refresh endpoint - deprecated.

    This endpoint is deprecated and will be removed after 2025-12-31.
    Please use POST /v1/auth/refresh instead.

    For backward compatibility, this endpoint redirects to the canonical
    auth route with deprecation tracking.
    """
    return await legacy_refresh(request, response)
