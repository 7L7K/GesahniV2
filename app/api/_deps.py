from fastapi import Depends, Request

from app.deps.scopes import (
    docs_security_with,
    optional_require_any_scope,
    require_any_scopes,
)

try:
    from app.security import require_nonce, verify_token  # type: ignore
except Exception:
    verify_token = None
    require_nonce = None

from app.security_ws import verify_ws

if not callable(verify_token):

    async def verify_token(*args, **kwargs):
        return None


if not callable(require_nonce):

    async def require_nonce(*args, **kwargs):
        return None


# Public: no auth.


def deps_protected_http():
    return [Depends(verify_token)]


def deps_admin_http():
    return [
        Depends(verify_token),
        Depends(require_any_scopes(["admin", "admin:write"])),
        Depends(docs_security_with(["admin:write"])),
    ]


def deps_ha_http():
    return [
        Depends(verify_token),
        Depends(require_any_scopes(["ha", "care:resident", "care:caregiver"])),
        Depends(docs_security_with(["care:resident"])),
    ]


def deps_music_http():
    return [
        Depends(verify_token),
        Depends(optional_require_any_scope(["music:control"])),
        Depends(docs_security_with(["music:control"])),
    ]


def dep_verify_ws():
    return Depends(verify_ws)


def require_admin_scope():
    """Simple dependency that checks if request has admin scope."""

    async def check_admin(request: Request):
        # First try to get user_id from JWT token directly
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(None, 1)[1].strip()
            try:
                import os

                from app.security import jwt_decode

                # Use central JWT decoder with issuer/audience/leeway support
                payload = jwt_decode(token, key=os.getenv("JWT_SECRET"), algorithms=["HS256"])
                scopes = payload.get("scopes", [])
                if isinstance(scopes, str):
                    scopes = [s.strip() for s in scopes.split()]
                if "admin" in scopes or "admin:write" in scopes:
                    return payload.get("sub") or payload.get("uid")
            except Exception:
                pass

        # Fallback to request.state
        user_scopes = getattr(request.state, "scopes", set())
        if "admin" in user_scopes or "admin:write" in user_scopes:
            return getattr(request.state, "user_id", None)

        from app.http_errors import http_error

        raise http_error(
            code="admin_scope_required", message="admin scope required", status=403
        )

    return Depends(check_admin)


def dep_nonce():
    return Depends(require_nonce)
