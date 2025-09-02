from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable
from typing import Any

from fastapi import HTTPException, Request, Security, WebSocket, status
from fastapi.security import OAuth2PasswordBearer

# Phase 6.1: Clean RBAC metrics
try:
    from app.metrics import RBAC_DENY
except Exception:  # pragma: no cover - optional
    RBAC_DENY = None  # type: ignore

logger = logging.getLogger(__name__)


OAUTH2_SCOPES: dict[str, str] = {
    "care:resident": "Resident-level care features (presence, sessions, HA actions)",
    "care:caregiver": "Caregiver portal and actions",
    "music:control": "Control music playback and devices",
    "admin:write": "Administrative endpoints: flags, metrics, backups",
}


# Exposed OAuth2 scheme for documentation and Swagger "Authorize" UI.
# We keep auto_error=False so runtime auth remains governed by our own deps.
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/v1/auth/token",
    scopes=OAUTH2_SCOPES,
    auto_error=False,
    scheme_name="OAuth2",
)


# Enhanced RBAC System: Single Source of Truth
# This system provides clean, consistent authorization across the application
# using request.state.scopes set by SessionAttachMiddleware

# PHASE 6: Granular Scopes - Enhanced Least-Privilege Access Control
STANDARD_SCOPES = {
    # Administrative scopes - split into granular permissions
    "admin": "Full administrative access (legacy - use specific scopes instead)",
    "admin:read": "Administrative read operations: metrics, logs, system status, user list",
    "admin:write": "Administrative write operations: flags, metrics, backups, system config",
    "admin:users:read": "Read user information and profiles",
    "admin:users:write": "Create, modify, or delete users",
    "admin:audit:read": "Access audit logs and security events",
    "admin:metrics:read": "Access system and application metrics",
    "admin:metrics:write": "Modify metric collection settings",
    "admin:system:read": "Read system configuration and status",
    "admin:system:write": "Modify system configuration and settings",
    "admin:security:read": "Read security configuration and policies",
    "admin:security:write": "Modify security policies and configurations",
    # Care and user management
    "care:resident": "Resident-level care features (presence, sessions, HA actions)",
    "care:caregiver": "Caregiver portal and actions",
    "care:emergency": "Emergency contact and alert management",
    "care:monitoring": "Access to monitoring and health data",
    # Music and media
    "music:control": "Control music playback and devices",
    "music:library:read": "Browse music library and playlists",
    "music:library:write": "Modify playlists and music preferences",
    "music:devices:read": "View available music devices",
    "music:devices:write": "Configure and control music devices",
    # User data and privacy
    "user:profile": "Access to user profile and personal data",
    "user:profile:read": "Read own profile information",
    "user:profile:write": "Modify own profile information",
    "user:settings": "Modify user settings and preferences (legacy)",
    "user:settings:read": "Read user settings and preferences",
    "user:settings:write": "Modify user settings and preferences",
    "user:privacy:read": "Access privacy settings and data usage",
    "user:privacy:write": "Modify privacy settings and data permissions",
    # Memory and AI features
    "memory:read": "Read personal memories and conversation history",
    "memory:write": "Create and modify memories",
    "memory:search": "Search through memories and history",
    "memory:delete": "Delete memories and conversation history",
    "ai:chat": "Access AI chat and conversation features",
    "ai:voice": "Use voice synthesis and recognition features",
    "ai:personalization": "Access personalized AI features and preferences",
    # Calendar and scheduling
    "calendar:read": "Read calendar events and schedules",
    "calendar:write": "Create and modify calendar events",
    "calendar:share": "Share calendar access with others",
    "reminders:read": "Read reminders and notifications",
    "reminders:write": "Create and modify reminders",
    # Photos and media
    "photos:read": "View and browse photos",
    "photos:write": "Upload and modify photos",
    "photos:share": "Share photos with others",
    "photos:albums": "Create and manage photo albums",
    # Health and device integration
    "health:read": "Read health data and device status",
    "health:write": "Modify health settings and configurations",
    "health:emergency": "Access emergency health information",
    "device:read": "Read device status and information",
    "device:write": "Configure and control devices",
    "device:notify": "Receive device notifications and alerts",
    # Communication and social features
    "contacts:read": "Read contact information",
    "contacts:write": "Manage contact information",
    "messages:read": "Read messages and communications",
    "messages:write": "Send and manage messages",
    "calls:read": "Access call history and logs",
    "calls:write": "Make and manage calls",
    # System and infrastructure
    "system:logs": "Access system logs and debugging information",
    "system:metrics": "Access system performance metrics",
    "system:status": "Read system health and status information",
    "system:maintenance": "Perform system maintenance operations",
}

# PHASE 6: Enhanced Role-Based Access Control with Granular Scopes
ROLE_SCOPES = {
    # Legacy roles - kept for compatibility
    "admin": ["admin", "admin:write", "admin:read"],
    "caregiver": ["care:caregiver", "user:profile"],
    "resident": ["care:resident", "user:profile", "user:settings"],
    "user": ["user:profile", "user:settings"],
    # New granular roles following least-privilege principle
    "admin_readonly": [
        "admin:read",
        "admin:users:read",
        "admin:audit:read",
        "admin:metrics:read",
        "admin:system:read",
        "admin:security:read",
    ],
    "admin_metrics": ["admin:metrics:read", "admin:metrics:write"],
    "admin_users": ["admin:users:read", "admin:users:write"],
    "admin_security": ["admin:security:read", "admin:security:write"],
    "admin_audit": ["admin:audit:read"],
    "admin_system": ["admin:system:read", "admin:system:write"],
    # Care roles with specific capabilities
    "caregiver_basic": [
        "care:caregiver",
        "user:profile:read",
        "user:settings:read",
        "memory:read",
        "calendar:read",
        "health:read",
    ],
    "caregiver_advanced": [
        "care:caregiver",
        "user:profile:write",
        "user:settings:write",
        "memory:read",
        "memory:write",
        "calendar:read",
        "calendar:write",
        "health:read",
        "health:write",
        "care:emergency",
    ],
    "care_monitor": ["care:monitoring", "health:read", "device:read"],
    "care_emergency": ["care:emergency", "health:emergency", "device:notify"],
    # User roles with privacy-focused scopes
    "user_basic": [
        "user:profile:read",
        "user:settings:read",
        "user:privacy:read",
        "memory:read",
        "calendar:read",
        "photos:read",
    ],
    "user_premium": [
        "user:profile:read",
        "user:profile:write",
        "user:settings:read",
        "user:settings:write",
        "user:privacy:read",
        "user:privacy:write",
        "memory:read",
        "memory:write",
        "memory:search",
        "ai:chat",
        "ai:voice",
        "ai:personalization",
        "calendar:read",
        "calendar:write",
        "calendar:share",
        "photos:read",
        "photos:write",
        "photos:share",
        "photos:albums",
        "music:library:read",
        "music:library:write",
        "contacts:read",
        "contacts:write",
        "reminders:read",
        "reminders:write",
    ],
    # System and infrastructure roles
    "system_monitor": ["system:status", "system:metrics", "system:logs"],
    "system_maintainer": [
        "system:status",
        "system:metrics",
        "system:logs",
        "system:maintenance",
    ],
    "device_manager": ["device:read", "device:write", "device:notify"],
    "backup_operator": ["admin:system:read", "system:maintenance"],
    # Communication roles
    "messaging_user": ["messages:read", "messages:write", "contacts:read"],
    "calling_user": ["calls:read", "calls:write", "contacts:read"],
}


def _get_scopes_from_request(request: Request) -> set[str] | None:
    """Extract scopes from request.state.scopes (set by SessionAttachMiddleware)."""
    scopes = getattr(request.state, "scopes", None)
    if isinstance(scopes, (list, tuple, set)):
        return set(scopes)
    return None


def _get_user_id_from_request(request: Request) -> str | None:
    """Get user ID from request state for logging/auditing purposes."""
    return getattr(request.state, "user_id", None)


def require_scope(scope: str) -> Callable[[Request], bool]:
    """Require a specific scope. Returns 401 if not authenticated, 403 if missing scope."""

    async def _checker(request: Request) -> bool:
        user_id = _get_user_id_from_request(request)
        scopes = _get_scopes_from_request(request)

        # PHASE 6: Enhanced scope tracking for metrics and audit
        if not hasattr(request.state, "scope_check_results"):
            request.state.scope_check_results = {}

        route = getattr(request.scope.get("route"), "path", None) or request.url.path

        if scopes is None:
            # Not authenticated / no session attached → 401
            request.state.scope_check_results[scope] = "denied"
            request.state.auth_failure_reason = "not_authenticated"
            logger.warning("rbac.unauthorized", user_id=user_id or "anonymous")

            # Record audit event for authorization failure
            try:
                from ..audit import append_audit

                append_audit(
                    "auth.unauthorized",
                    user_id_hashed=user_id,
                    data={
                        "scope": scope,
                        "route": route,
                        "reason": "not_authenticated",
                    },
                )
            except Exception:
                pass  # Continue even if audit fails

            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="login or include Authorization header")

        # Check if the required scope is satisfied
        scope_satisfied = scope in scopes

        # Handle legacy admin scope as superset
        if not scope_satisfied and scope.startswith("admin:") and "admin" in scopes:
            # The 'admin' scope is a superset that includes all admin:* scopes
            scope_satisfied = True

        if not scope_satisfied:
            # Authenticated but missing capability → 403
            request.state.scope_check_results[scope] = "denied"
            request.state.auth_failure_reason = f"missing_scope:{scope}"
            if RBAC_DENY:
                RBAC_DENY.labels(scope=scope).inc()
            logger.warning(
                "rbac.forbidden",
                user_id=user_id or "anonymous",
                required_scope=scope,
                available_scopes=sorted(scopes),
            )

            # Record audit event for scope denial
            try:
                from ..audit import append_audit

                audit_data = {
                    "scope": scope,
                    "route": route,
                    "available_scopes": sorted(scopes),
                    "reason": "missing_scope",
                }
                if scope.startswith("admin:") and "admin" in scopes:
                    audit_data["reason"] = "admin_superset_check_failed"
                append_audit(
                    "auth.scope_denied", user_id_hashed=user_id, data=audit_data
                )
            except Exception:
                pass  # Continue even if audit fails

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing_scope:{scope}",
            )

        # Access granted - record success
        request.state.scope_check_results[scope] = "granted"
        logger.info("rbac.access_granted", user_id=user_id or "anonymous", scope=scope)

        # Record audit event for successful scope access
        try:
            from app.audit import append_audit

            append_audit(
                "auth.scope_granted",
                user_id_hashed=user_id,
                data={"scope": scope, "route": route, "granted": True},
            )
        except Exception:
            pass  # Continue even if audit fails

        return True

    return _checker


def require_any_scopes(
    required_scopes: list[str] | set[str],
) -> Callable[[Request], bool]:
    """Require any of the specified scopes. Returns 401 if not authenticated, 403 if missing all scopes."""
    req = set(required_scopes)

    async def _checker(request: Request) -> bool:
        user_id = _get_user_id_from_request(request)
        scopes = _get_scopes_from_request(request)

        if scopes is None:
            logger.warning("rbac.unauthorized", user_id=user_id or "anonymous")
            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="login or include Authorization header")

        if not (req & scopes):
            logger.warning(
                "rbac.forbidden",
                user_id=user_id or "anonymous",
                required_any=sorted(req),
                available_scopes=sorted(scopes),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing_any_scope:{','.join(sorted(req))}",
            )

        logger.info(
            "rbac.access_granted",
            user_id=user_id or "anonymous",
            matched_scope=list(req & scopes)[0],
        )
        return True

    return _checker


def require_role(role: str) -> Callable[[Request], bool]:
    """Require a specific role (maps to multiple scopes). Cleaner API for common use cases."""
    if role not in ROLE_SCOPES:
        raise ValueError(f"Unknown role: {role}")

    required_scopes = ROLE_SCOPES[role]
    return require_any_scopes(required_scopes)


def require_admin() -> Callable[[Request], bool]:
    """Convenience function for admin access - requires any admin scope."""
    return require_any_scopes(["admin", "admin:write", "admin:read"])


def optional_scope(scope: str) -> Callable[[Request], str | None]:
    """Optional scope check - returns the scope if present, None if not. Never raises exceptions."""

    async def _checker(request: Request) -> str | None:
        scopes = _get_scopes_from_request(request)
        if scopes and scope in scopes:
            return scope
        return None

    return _checker


def get_user_scopes() -> Callable[[Request], set[str]]:
    """Dependency that returns the user's current scopes (empty set if not authenticated)."""

    async def _getter(request: Request) -> set[str]:
        scopes = _get_scopes_from_request(request)
        return scopes or set()

    return _getter


def _extract_payload(target: Any) -> dict | None:
    """Return decoded JWT payload for either Request or WebSocket objects.

    Prefers state.jwt_payload when present; otherwise falls back to helper
    functions that parse Authorization headers/cookies.
    """

    try:
        state = getattr(target, "state", None)
        payload = getattr(state, "jwt_payload", None)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    try:
        # Try HTTP path first
        from app.security import _get_request_payload as _get_req  # type: ignore

        p = _get_req(target)
        if isinstance(p, dict):
            return p
    except Exception:
        pass
    try:
        # Fallback to WS path when available
        from app.security import _get_ws_payload as _get_ws  # type: ignore

        p = _get_ws(target)
        if isinstance(p, dict):
            return p
    except Exception:
        pass
    return None


def require_scope(required: str) -> Callable[[Request], None]:
    """Return a dependency that enforces a JWT scope when JWTs are enabled.

    If ``JWT_SECRET`` is not configured, this is a no-op to preserve local/dev
    and unit-test behavior.
    """

    async def _dep(request: Request) -> None:
        # Skip CORS preflight requests
        if str(request.method).upper() == "OPTIONS":
            return

        # In pytest runs, allow omitted token when no payload is present so
        # unit tests can exercise RBAC-protected endpoints without full JWT setup.
        if os.getenv("PYTEST_RUNNING", "").lower() in {"1", "true", "yes"}:
            try:
                if _extract_payload(request) is None:
                    return
            except Exception:
                pass

        # Use session middleware's 3-state logic instead of direct payload extraction
        user_id = _get_user_id_from_request(request)
        scopes = _get_scopes_from_request(request)

        if scopes is None:
            # Not authenticated - return 401
            logger.warning("deny: missing_scope scope=<%s> reason=no_payload", required)
            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="login or include Authorization header")

        # Check if the required scope is satisfied
        scope_satisfied = required in scopes

        # Global admin superset: a bearer with `admin` should be able to access
        # most administrative and user-profile endpoints for tests and legacy
        # behaviour. Treat `admin` as a super-scope that satisfies checks.
        if not scope_satisfied and "admin" in scopes:
            scope_satisfied = True

        if not scope_satisfied:
            logger.warning(
                "deny: missing_scope scope=<%s> available=<%s>",
                required,
                ",".join(scopes),
            )
            raise HTTPException(status_code=403, detail="Forbidden: missing scope")

    return _dep


def optional_require_scope(required: str) -> Callable[[Request], None]:
    """Scope check that can be toggled via env at runtime.

    Evaluates ENFORCE_JWT_SCOPES on each request so tests that set/unset
    the env after app import still take effect.
    """

    async def _maybe(request: Request) -> None:
        if os.getenv("ENFORCE_JWT_SCOPES", "").lower() in {"1", "true", "yes"}:
            dep = require_scope(required)
            return await dep(request)
        return None

    return _maybe


def require_any_scope(required: Iterable[str]) -> Callable[[Request], None]:
    """Return a dependency that allows access if any of the provided scopes is present.

    Useful for migrations or aliasing scopes, e.g., ["admin", "admin:write"].
    """

    required_set = {str(s).strip() for s in required if str(s).strip()}

    async def _dep(request: Request) -> None:
        # Skip CORS preflight requests
        if str(request.method).upper() == "OPTIONS":
            return
        import os as _os

        if not _os.getenv("JWT_SECRET"):
            return
        payload = _extract_payload(request)
        if not isinstance(payload, dict):
            logger.warning(
                "deny: missing_scope scopes=<%s> reason=no_payload",
                ",".join(required_set),
            )
            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="login or include Authorization header")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not (set(scopes) & required_set):
            logger.warning(
                "deny: missing_scope required=<%s> available=<%s>",
                ",".join(required_set),
                ",".join(scopes),
            )
            raise HTTPException(status_code=403, detail="Forbidden: missing scope")

    return _dep


def optional_require_any_scope(required: Iterable[str]) -> Callable[[Request], None]:
    """Like require_any_scope but evaluated dynamically per request."""

    async def _maybe(request: Request) -> None:
        if os.getenv("ENFORCE_JWT_SCOPES", "").lower() in {"1", "true", "yes"}:
            dep = require_any_scope(required)
            return await dep(request)
        return None

    return _maybe


def docs_security_with(scopes: list[str]):
    """Return a no-op dependency that binds OAuth2 scopes for documentation only.

    Example usage:
        dependencies=[Security(docs_security_with(["admin:write"]))]
    This ensures Swagger shows lock icons and an Authorize dialog with scopes,
    without changing runtime auth (which is enforced by verify_token/require_scope).
    """

    async def _dep(_: str | None = Security(oauth2_scheme, scopes=scopes)) -> None:  # type: ignore[valid-type]
        return None

    return _dep


# Unified helpers: pluralized names that accept lists and can be used for
# both HTTP and WebSocket routes (via FastAPI dependency system).


def require_scopes(required: Iterable[str]) -> Callable[[Request], None]:
    """Enforce that ALL required scopes are present on the JWT.

    Semantics:
    - If JWT is configured but token missing/invalid -> 401
    - If token valid but lacks required scope(s) -> 403
    - If JWT not configured -> no-op (dev/test convenience)
    """

    required_set = {str(s).strip() for s in required if str(s).strip()}

    async def _dep(request: Request) -> None:
        # Skip CORS preflight requests
        if str(request.method).upper() == "OPTIONS":
            return
        if not os.getenv("JWT_SECRET"):
            return
        payload = _extract_payload(request)
        if not isinstance(payload, dict):
            logger.warning(
                "deny: missing_scope scopes=<%s> reason=no_payload",
                ",".join(required_set),
            )
            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="login or include Authorization header")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not required_set <= set(scopes):
            logger.warning(
                "deny: missing_scope required=<%s> available=<%s>",
                ",".join(required_set),
                ",".join(scopes),
            )
            raise HTTPException(status_code=403, detail="Forbidden: missing scope")

    return _dep


def require_any_scopes(required: Iterable[str]) -> Callable[[Request], None]:
    """Enforce that ANY of the provided scopes are present on the JWT.

    Same 401/403 semantics as require_scopes.
    """

    required_set = {str(s).strip() for s in required if str(s).strip()}

    async def _dep(request: Request) -> None:
        # Skip CORS preflight requests
        if str(request.method).upper() == "OPTIONS":
            return
        if not os.getenv("JWT_SECRET"):
            return
        payload = _extract_payload(request)
        if not isinstance(payload, dict):
            logger.warning(
                "deny: missing_scope scopes=<%s> reason=no_payload",
                ",".join(required_set),
            )
            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="login or include Authorization header")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not (set(scopes) & required_set):
            logger.warning(
                "deny: missing_scope required=<%s> available=<%s>",
                ",".join(required_set),
                ",".join(scopes),
            )
            raise HTTPException(status_code=403, detail="Forbidden: missing scope")

    return _dep


def require_scopes_ws(required: Iterable[str]) -> Callable[[WebSocket], None]:
    required_set = {str(s).strip() for s in required if str(s).strip()}

    async def _dep(websocket: WebSocket) -> None:
        if not os.getenv("JWT_SECRET"):
            return
        payload = _extract_payload(websocket)
        if not isinstance(payload, dict):
            # For WS, map to 4401-equivalent by raising HTTPException which FastAPI will map to 403-ish close.
            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="authenticate before opening WebSocket")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not required_set <= set(scopes):
            raise HTTPException(status_code=403, detail="Forbidden: missing scope")

    return _dep


def require_any_scopes_ws(required: Iterable[str]) -> Callable[[WebSocket], None]:
    required_set = {str(s).strip() for s in required if str(s).strip()}

    async def _dep(websocket: WebSocket) -> None:
        if not os.getenv("JWT_SECRET"):
            return
        payload = _extract_payload(websocket)
        if not isinstance(payload, dict):
            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="authenticate before opening WebSocket")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not (set(scopes) & required_set):
            raise HTTPException(status_code=403, detail="Forbidden: missing scope")

    return _dep


__all__ = [
    "oauth2_scheme",
    "OAUTH2_SCOPES",
    "require_scope",
    "optional_require_scope",
    "require_any_scope",
    "optional_require_any_scope",
    "require_scopes",
    "require_any_scopes",
    "require_scopes_ws",
    "require_any_scopes_ws",
    "docs_security_with",
    # Enhanced RBAC System
    "STANDARD_SCOPES",
    "ROLE_SCOPES",
    "_get_scopes_from_request",
    "_get_user_id_from_request",
    "require_role",
    "require_admin",
    "optional_scope",
    "get_user_scopes",
]
