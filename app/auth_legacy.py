"""Thin redirect routes for legacy auth endpoints.

All business logic moved to app.api.auth as canonical source of truth.
This module provides 308 Permanent Redirects to maintain compatibility.
"""

from fastapi import APIRouter

router = APIRouter()

# Backward compatibility constants - DO NOT USE in new code
# These exist only for legacy imports and should be removed once all imports are updated
EXPIRE_MINUTES = 30
REFRESH_EXPIRE_MINUTES = 1440


# Backward compatibility functions - DO NOT USE in new code
def _create_session_id(jti: str, expires_at: float) -> str:
    """Legacy session creation - use canonical auth module instead."""
    from app.session_store import get_session_store

    store = get_session_store()
    return store.create_session(jti, expires_at)


def _verify_session_id(session_id: str, jti: str) -> bool:
    """Legacy session verification - use canonical auth module instead."""
    from app.session_store import get_session_store

    store = get_session_store()
    stored_jti = store.get_session(session_id)
    return stored_jti == jti


# Backward compatibility password context - DO NOT USE in new code
try:
    from passlib.context import CryptContext

    pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
except Exception:
    pwd_context = None


# Only keep routes that don't conflict with canonical routes
# /login, /register, /forgot, /reset_password conflict with canonical routes
# So only keep routes that are truly legacy/unused
