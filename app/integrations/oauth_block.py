from __future__ import annotations
import logging
import os
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/oauth", tags=["oauth"])

@router.api_route("/{_any:path}", methods=["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"])
def oauth_disabled(_any: str):
    if os.getenv("DEMO_MODE") == "1":
        logger.warning(f"🚫 DEMO OAUTH: Blocking OAuth request to '/v1/oauth/{_any}' in demo mode")
        raise HTTPException(status_code=503, detail="OAuth disabled in Demo Mode")
    logger.info(f"🔓 OAUTH: Allowing OAuth request to '/v1/oauth/{_any}' (demo mode off)")
    return {"detail": "OAuth placeholder (Demo Mode off)."}
