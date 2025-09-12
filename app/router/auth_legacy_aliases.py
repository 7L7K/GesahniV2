"""Legacy auth route aliases with tracking.

This router provides backward compatibility for clients still using the old
/v1/* auth endpoints by redirecting them to the canonical /v1/auth/* routes
with deprecation headers, logging, and metrics tracking.
"""
from fastapi import APIRouter, Request, Response

from ..api.auth import login_v1, logout, refresh, register_v1, whoami
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
                    "schema": {"example": {"access_token": "jwt_token", "refresh_token": "refresh_jwt"}}
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


# Legacy route: POST /v1/register → POST /v1/auth/register
legacy_register = LegacyAlias("/register", "/v1/auth/register", "POST", register_v1)

@router.post(
    "/register",
    deprecated=True,
    include_in_schema=True,
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {"example": {"access_token": "jwt", "refresh_token": "jwt"}}
                }
            }
        },
        400: {"description": "invalid or username_taken"},
    },
)
async def legacy_register_handler(request: Request, response: Response):
    """Legacy register endpoint - deprecated.

    This endpoint is deprecated and will be removed after 2025-12-31.
    Please use POST /v1/auth/register instead.

    For backward compatibility, this endpoint redirects to the canonical
    auth route with deprecation tracking.
    """
    return await legacy_register(request, response)


# Legacy route: GET /v1/whoami → GET /v1/auth/whoami
legacy_whoami_wrapper = LegacyAlias("/whoami", "/v1/auth/whoami", "GET", whoami)

@router.get(
    "/whoami",
    deprecated=True,
    include_in_schema=True
)
async def legacy_whoami_handler(request: Request):
    """Legacy whoami endpoint - deprecated.

    This endpoint is deprecated and will be removed after 2025-12-31.
    Please use GET /v1/auth/whoami instead.

    For backward compatibility, this endpoint redirects to the canonical
    auth route with deprecation tracking.
    """
    return await legacy_whoami_wrapper(request)


# Legacy route: POST /v1/logout → POST /v1/auth/logout
legacy_logout = LegacyAlias("/logout", "/v1/auth/logout", "POST", logout)

@router.post(
    "/logout",
    deprecated=True,
    include_in_schema=True,
    responses={
        200: {
            "content": {
                "application/json": {
                    "schema": {"example": {"message": "logged out"}}
                }
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
                    "schema": {"example": {"access_token": "jwt_token", "refresh_token": "refresh_jwt"}}
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
