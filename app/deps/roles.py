from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException, Request

from app.security import _get_request_payload as _get_req_payload  # type: ignore
from app.security import _payload_scopes as _payload_scopes

from .user import get_current_user_id


def _normalize_roles(obj) -> set[str]:
    if obj is None:
        return set()
    if isinstance(obj, str):
        return {obj.strip().lower()} if obj.strip() else set()
    if isinstance(obj, (list, tuple, set)):
        return {str(x).strip().lower() for x in obj if str(x).strip()}
    return set()


def _extract_roles(request: Request) -> set[str]:
    # 1) Prefer roles set by upstream auth dependencies (e.g., Clerk JWT)
    try:
        state_roles = getattr(request.state, "roles", None)
        roles = _normalize_roles(state_roles)
        if roles:
            return roles
    except Exception:
        pass
    # 2) Inspect JWT payload for a 'roles' claim
    try:
        payload = getattr(request.state, "jwt_payload", None)
        if not isinstance(payload, dict):
            payload = _get_req_payload(request)
        if isinstance(payload, dict):
            roles = _normalize_roles(payload.get("roles") or payload.get("role"))
            if roles:
                return roles
            # Fallback: map scopes to roles
            scopes = _payload_scopes(payload)
            mapped = set()
            if "admin" in scopes or "admin:write" in scopes:
                mapped.add("admin")
            if "care:caregiver" in scopes:
                mapped.add("caregiver")
            if "care:resident" in scopes:
                mapped.add("resident")
            if mapped:
                return mapped
    except Exception:
        pass
    return set()


def has_roles(
    request: Request, required: Iterable[str], *, any_of: bool = True
) -> bool:
    roles = _extract_roles(request)
    wanted = {str(r).strip().lower() for r in required if str(r).strip()}
    if not wanted:
        return True
    if any_of:
        return bool(roles & wanted)
    return wanted.issubset(roles)


def require_roles(required: Iterable[str], *, any_of: bool = True):
    async def _dep(request: Request) -> None:
        # Skip CORS preflight requests
        if request.method == "OPTIONS":
            return
        # Ensure authentication was established (401 if not)
        # Use resolve_user_id helper to avoid raising in dependency construction
        try:
            from .user import resolve_user_id

            user_id = resolve_user_id(request=request)
        except Exception:
            user_id = get_current_user_id(request=request)
        if not user_id or user_id == "anon":
            from ..http_errors import unauthorized

            raise unauthorized(message="authentication required", hint="login or include Authorization header")
        # Authorize based on roles (403 if missing)
        if not has_roles(request, required, any_of=any_of):
            raise HTTPException(status_code=403, detail="forbidden")
        return None

    return _dep


__all__ = ["require_roles", "has_roles"]
