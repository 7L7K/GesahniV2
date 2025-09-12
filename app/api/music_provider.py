from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from ..auth_store_tokens import mark_invalid
from ..deps.user import get_current_user_id

router = APIRouter()
logger = logging.getLogger(__name__)


@router.delete("/api/provider/{provider}/disconnect")
async def provider_disconnect(provider: str, user_id: str = Depends(get_current_user_id)):
    """Generic provider disconnect: revoke best-effort and clear stored tokens."""
    try:
        success = await mark_invalid(user_id, provider)
        if not success:
            logger.warning("Token for %s@%s was not found or already invalid", provider, user_id)
    except Exception:
        logger.exception("provider.disconnect failed for %s@%s", provider, user_id)
    return {"ok": True}


