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


__all__ = ["require_scope"]


