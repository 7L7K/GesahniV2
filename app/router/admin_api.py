"""Admin API routes for the router.

This module defines /v1/admin/* routes.
Leaf module - no imports from app/router/__init__.py.
"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Create the router
router = APIRouter(tags=["Admin"])


# Admin scope requirement - proper implementation with 403 responses
def require_admin():
    """Require admin scope - raises 403 for unauthorized access."""
    async def dependency(request: Request):
        # Use new auth contract helper for consistent 401/403 handling
        from app.security.auth_contract import require_auth
        await require_auth(request, required_scopes=["admin:read"])
        return request
    return dependency


def require_scope(scope: str):
    """Require specific scope - raises 403 for unauthorized access."""
    async def dependency(request: Request):
        # Use new auth contract helper for consistent 401/403 handling
        from app.security.auth_contract import require_auth
        await require_auth(request, required_scopes=[scope])
        return request
    return dependency


@router.get("/ping", dependencies=[Depends(require_admin())])
async def admin_ping():
    """Simple admin ping endpoint."""
    return {
        "status": "ok",
        "service": "router_admin",
        "timestamp": "2024-01-01T00:00:00Z",
    }


@router.get("/rbac/info", dependencies=[Depends(require_scope("admin:read"))])
async def admin_rbac_info():
    """Get RBAC information."""
    return {
        "rbac_enabled": True,
        "scopes": ["admin:read", "admin:write", "chat:write"],
        "note": "RBAC info not fully implemented in leaf module",
    }


@router.get("/system/status", dependencies=[Depends(require_scope("admin:read"))])
async def admin_system_status():
    """Get system status information."""
    return {
        "status": "operational",
        "version": "1.0.0",
        "uptime": "unknown",
        "note": "System status not fully implemented in leaf module",
    }


@router.get("/tokens/google", dependencies=[Depends(require_scope("admin:read"))])
async def admin_google_tokens():
    """Get Google OAuth tokens for debugging."""
    return {
        "tokens": [],
        "note": "Google tokens not implemented in leaf module",
    }


@router.get("/metrics", dependencies=[Depends(require_scope("admin:read"))])
async def admin_metrics():
    """Get application metrics."""
    return {
        "metrics": {},
        "note": "Metrics collection not implemented in leaf module",
    }


@router.get("/router/decisions", dependencies=[Depends(require_scope("admin:read"))])
async def admin_router_decisions():
    """Get recent router decisions."""
    return {
        "decisions": [],
        "note": "Router decisions logging not implemented in leaf module",
    }


@router.get("/config", dependencies=[Depends(require_scope("admin:read"))])
async def admin_config():
    """Get application configuration."""
    return {
        "config": {},
        "note": "Config dumping not implemented in leaf module",
    }


@router.get("/errors", dependencies=[Depends(require_scope("admin:read"))])
async def admin_errors():
    """Get recent application errors."""
    return {
        "errors": [],
        "note": "Error collection not implemented in leaf module",
    }


@router.get("/flags", dependencies=[Depends(require_scope("admin:read"))])
async def admin_flags_get():
    """Get feature flags."""
    return {
        "flags": {},
        "note": "Feature flags not implemented in leaf module",
    }


@router.post("/flags", dependencies=[Depends(require_scope("admin:write"))])
async def admin_flags_post(request: Request):
    """Update feature flags."""
    try:
        # Parse the request body
        body = await request.json()
        flags = body.get("flags", {})

        # In a real implementation, you would update the flags
        # For now, just return success
        return {
            "status": "updated",
            "flags": flags,
            "note": "Feature flags update not fully implemented in leaf module",
        }
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid request format", "detail": str(e)}
        )
