from __future__ import annotations

import os
import logging
from typing import Any, Callable, Iterable, List

from fastapi import HTTPException, Request, Security, WebSocket
from fastapi.security import OAuth2PasswordBearer

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
        # Only enforce when a JWT is in play
        if not os.getenv("JWT_SECRET"):
            return
        payload = _extract_payload(request)
        if not isinstance(payload, dict):
            # verify_token dependency should have populated this already
            logger.warning("deny: missing_scope scope=<%s> reason=no_payload", required)
            raise HTTPException(status_code=401, detail="Unauthorized")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if required not in set(scopes):
            logger.warning("deny: missing_scope scope=<%s> available=<%s>", required, ",".join(scopes))
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
            logger.warning("deny: missing_scope scopes=<%s> reason=no_payload", ",".join(required_set))
            raise HTTPException(status_code=401, detail="Unauthorized")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not (set(scopes) & required_set):
            logger.warning("deny: missing_scope required=<%s> available=<%s>", ",".join(required_set), ",".join(scopes))
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


def docs_security_with(scopes: List[str]):
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
            logger.warning("deny: missing_scope scopes=<%s> reason=no_payload", ",".join(required_set))
            raise HTTPException(status_code=401, detail="Unauthorized")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not required_set <= set(scopes):
            logger.warning("deny: missing_scope required=<%s> available=<%s>", ",".join(required_set), ",".join(scopes))
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
            logger.warning("deny: missing_scope scopes=<%s> reason=no_payload", ",".join(required_set))
            raise HTTPException(status_code=401, detail="Unauthorized")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not (set(scopes) & required_set):
            logger.warning("deny: missing_scope required=<%s> available=<%s>", ",".join(required_set), ",".join(scopes))
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
            raise HTTPException(status_code=401, detail="Unauthorized")
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
            raise HTTPException(status_code=401, detail="Unauthorized")
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
]


