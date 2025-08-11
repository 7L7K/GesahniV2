"""Device trust/session rotation for Granny Mode.

Separate from `app/auth.py` to avoid conflicts. Provides a router for trusted
device sessions without interactive login on the TV.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/device", tags=["auth"])


@router.get("/session")
async def get_device_session() -> dict:
    # Placeholder: returns a synthetic long-lived session with rotation marker
    return {"status": "ok", "session": {"trusted": True, "rotate_after": 86400}}


