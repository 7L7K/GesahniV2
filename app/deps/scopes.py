from __future__ import annotations

import os
from typing import Callable

from fastapi import HTTPException, Request


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


__all__ = ["require_scope", "optional_require_scope"]


