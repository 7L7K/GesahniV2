"""Legacy auth compatibility shim.

This module provides backward compatibility for legacy auth routes by redirecting
them to the canonical /v1/auth/* endpoints with proper deprecation signaling.

All real auth logic has been moved to app.auth.endpoints.* - this file only
contains 308 redirects for backward compatibility.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse

from ..metrics.auth import AUTH_LEGACY_SHIM_TOTAL
logger = logging.getLogger(__name__)

# Legacy compatibility router - all routes hidden from schema
router = APIRouter(tags=["Auth Legacy"], include_in_schema=False)

# Sunset date for legacy auth routes 
SUNSET_DATE = "Wed, 31 Dec 2025 23:59:59 GMT"

def _legacy_redirect(
    canonical_path: str, legacy_path: str, *, request: Request | None = None
) -> RedirectResponse:
    """Create a 308 redirect with deprecation headers and logging."""
    # Log legacy usage for observability
    logger.warning(
        "LEGACY_AUTH_ROUTE_USED",
        extra={
            "legacy_path": legacy_path,
            "canonical_path": canonical_path,
            "sunset": "2025-12-31",
        },
    )
    try:
        path_label = request.url.path if request is not None else legacy_path
    except Exception:
        path_label = legacy_path
    AUTH_LEGACY_SHIM_TOTAL.labels(path=path_label).inc()

    # Track legacy usage metrics
    try:
        from ..metrics import LEGACY_HITS
        LEGACY_HITS.labels(endpoint=legacy_path).inc()
    except ImportError:
        pass
    
    # Create redirect with deprecation headers
    response = RedirectResponse(canonical_path, status_code=308)
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = SUNSET_DATE
    response.headers["Link"] = f'<{canonical_path}>; rel="successor-version"'
    response.headers["X-Deprecated-Path"] = "1"
    
    return response


# Legacy auth routes that compete with canonical /v1/auth/* routes
@router.post("/auth/login") 
async def legacy_auth_login(request: Request):
    """Legacy /auth/login endpoint - redirects to /v1/auth/login."""
    return _legacy_redirect("/v1/auth/login", "/auth/login", request=request)


@router.post("/auth/logout")
async def legacy_auth_logout(request: Request):
    """Legacy /auth/logout endpoint - redirects to /v1/auth/logout.""" 
    return _legacy_redirect("/v1/auth/logout", "/auth/logout", request=request)


@router.post("/auth/refresh")
async def legacy_auth_refresh(request: Request):
    """Legacy /auth/refresh endpoint - redirects to /v1/auth/refresh."""
    return _legacy_redirect("/v1/auth/refresh", "/auth/refresh", request=request)


@router.post("/auth/logout_all")
async def legacy_auth_logout_all(request: Request):
    """Legacy /auth/logout_all endpoint - redirects to /v1/auth/logout_all."""
    return _legacy_redirect("/v1/auth/logout_all", "/auth/logout_all", request=request)


@router.post("/auth/token")
async def legacy_auth_token(request: Request):
    """Legacy /auth/token endpoint - redirects to /v1/auth/token."""
    return _legacy_redirect("/v1/auth/token", "/auth/token", request=request)


@router.get("/auth/examples")
async def legacy_auth_examples(request: Request):
    """Legacy /auth/examples endpoint - redirects to /v1/auth/examples."""
    return _legacy_redirect("/v1/auth/examples", "/auth/examples", request=request)


@router.post("/register")
async def legacy_register(request: Request):
    """Legacy /register endpoint - redirects to /v1/auth/register."""
    return _legacy_redirect("/v1/auth/register", "/register", request=request)


# Re-export canonical handlers for backward compatibility with deprecation warnings
warnings.warn(
    "DEPRECATED: app.api.auth_shim is deprecated. Import from app.auth.endpoints.* instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Import and re-export with deprecation wrapper
from app.auth.endpoints.debug import debug_auth_state, debug_cookies, whoami
from app.auth.endpoints.login import login, login_v1  
from app.auth.endpoints.logout import logout, logout_all
from app.auth.endpoints.refresh import refresh, rotate_refresh_cookies
from app.auth.endpoints.register import register_v1
from app.auth.endpoints.token import dev_token, token_examples


class _DeprecatedAccess:
    """Wrapper to emit deprecation warnings on access."""
    
    def __init__(self, func: Any, name: str, message: str):
        self.func = func
        self.name = name
        self.message = message
    
    def __call__(self, *args, **kwargs):
        warnings.warn(self.message, DeprecationWarning, stacklevel=2)
        return self.func(*args, **kwargs)
    
    def __getattr__(self, name):
        warnings.warn(self.message, DeprecationWarning, stacklevel=2)
        return getattr(self.func, name)


# Wrap all legacy exports
login = _DeprecatedAccess(
    login,
    "login", 
    "DEPRECATED: app.api.auth_shim.login is deprecated. Import from app.auth.endpoints.login instead.",
)

login_v1 = _DeprecatedAccess(
    login_v1,
    "login_v1",
    "DEPRECATED: app.api.auth_shim.login_v1 is deprecated. Import from app.auth.endpoints.login instead.",
)

register_v1 = _DeprecatedAccess(
    register_v1,
    "register_v1",
    "DEPRECATED: app.api.auth_shim.register_v1 is deprecated. Import from app.auth.endpoints.register instead.",
)

refresh = _DeprecatedAccess(
    refresh,
    "refresh",
    "DEPRECATED: app.api.auth_shim.refresh is deprecated. Import from app.auth.endpoints.refresh instead.",
)

rotate_refresh_cookies = _DeprecatedAccess(
    rotate_refresh_cookies,
    "rotate_refresh_cookies",
    "DEPRECATED: app.api.auth_shim.rotate_refresh_cookies is deprecated. Import from app.auth.endpoints.refresh instead.",
)

logout = _DeprecatedAccess(
    logout,
    "logout",
    "DEPRECATED: app.api.auth_shim.logout is deprecated. Import from app.auth.endpoints.logout instead.",
)

logout_all = _DeprecatedAccess(
    logout_all,
    "logout_all",
    "DEPRECATED: app.api.auth_shim.logout_all is deprecated. Import from app.auth.endpoints.logout instead.",
)

dev_token = _DeprecatedAccess(
    dev_token,
    "dev_token",
    "DEPRECATED: app.api.auth_shim.dev_token is deprecated. Import from app.auth.endpoints.token instead.",
)

token_examples = _DeprecatedAccess(
    token_examples,
    "token_examples",
    "DEPRECATED: app.api.auth_shim.token_examples is deprecated. Import from app.auth.endpoints.token instead.",
)

debug_cookies = _DeprecatedAccess(
    debug_cookies,
    "debug_cookies",
    "DEPRECATED: app.api.auth_shim.debug_cookies is deprecated. Import from app.auth.endpoints.debug instead.",
)

debug_auth_state = _DeprecatedAccess(
    debug_auth_state,
    "debug_auth_state",
    "DEPRECATED: app.api.auth_shim.debug_auth_state is deprecated. Import from app.auth.endpoints.debug instead.",
)

whoami = _DeprecatedAccess(
    whoami,
    "whoami",
    "DEPRECATED: app.api.auth_shim.whoami is deprecated. Import from app.auth.endpoints.debug instead.",
)
