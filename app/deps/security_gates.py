from __future__ import annotations

from fastapi import Depends, HTTPException

from app.security import verify_token


def has_scopes(user: dict | None, scopes: list[str]) -> bool:
    if not isinstance(user, dict):
        return False
    raw = user.get("scope") or user.get("scopes") or []
    if isinstance(raw, str):
        owned = {s.strip() for s in raw.split() if s.strip()}
    else:
        owned = {str(s).strip() for s in raw}
    return set(scopes).issubset(owned)

def require_scopes(scopes: list[str]):
    def _gate(user=Depends(verify_token)):
        if not has_scopes(getattr(user, "state", None) or getattr(user, "jwt_payload", None) or user, scopes):
            raise HTTPException(status_code=403, detail="forbidden")
        return user
    return _gate

__all__ = ["require_scopes", "has_scopes"]


