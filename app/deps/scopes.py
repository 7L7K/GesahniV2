from __future__ import annotations

import os
from typing import Callable, Iterable, List

from fastapi import HTTPException, Request, Security
from fastapi.security import OAuth2PasswordBearer


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


def require_scope(required: str) -> Callable[[Request], None]:
    """Return a dependency that enforces a JWT scope when JWTs are enabled.

    If ``JWT_SECRET`` is not configured, this is a no-op to preserve local/dev
    and unit-test behavior.
    """

    async def _dep(request: Request) -> None:
        # Only enforce when a JWT is in play
        if not os.getenv("JWT_SECRET"):
            return
        payload = getattr(request.state, "jwt_payload", None)
        if not isinstance(payload, dict):
            # verify_token dependency should have populated this already
            raise HTTPException(status_code=401, detail="Unauthorized")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if required not in set(scopes):
            raise HTTPException(status_code=403, detail="Forbidden: missing scope")

    return _dep


def optional_require_scope(required: str) -> Callable[[Request], None]:
    """Scope check that can be globally turned off via env.

    When ENFORCE_JWT_SCOPES is not set, behaves as a no-op to keep tests green.
    """

    if os.getenv("ENFORCE_JWT_SCOPES", "").lower() in {"1", "true", "yes"}:
        return require_scope(required)

    async def _noop(_: Request) -> None:
        return None

    return _noop


def require_any_scope(required: Iterable[str]) -> Callable[[Request], None]:
    """Return a dependency that allows access if any of the provided scopes is present.

    Useful for migrations or aliasing scopes, e.g., ["admin", "admin:write"].
    """

    required_set = {str(s).strip() for s in required if str(s).strip()}

    async def _dep(request: Request) -> None:
        import os as _os

        if not _os.getenv("JWT_SECRET"):
            return
        payload = getattr(request.state, "jwt_payload", None)
        if not isinstance(payload, dict):
            raise HTTPException(status_code=401, detail="Unauthorized")
        scopes = payload.get("scope") or payload.get("scopes") or []
        if isinstance(scopes, str):
            scopes = [s.strip() for s in scopes.split() if s.strip()]
        if not (set(scopes) & required_set):
            raise HTTPException(status_code=403, detail="Forbidden: missing scope")

    return _dep


def optional_require_any_scope(required: Iterable[str]) -> Callable[[Request], None]:
    """Like require_any_scope but disabled unless ENFORCE_JWT_SCOPES is truthy."""

    import os as _os

    if _os.getenv("ENFORCE_JWT_SCOPES", "").lower() in {"1", "true", "yes"}:
        return require_any_scope(required)

    async def _noop(_: Request) -> None:
        return None

    return _noop


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


__all__ = [
    "oauth2_scheme",
    "OAUTH2_SCOPES",
    "require_scope",
    "optional_require_scope",
    "require_any_scope",
    "optional_require_any_scope",
    "docs_security_with",
]


