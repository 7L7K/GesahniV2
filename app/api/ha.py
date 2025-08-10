from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.deps.user import get_current_user_id
from app.security import require_nonce
from app.home_assistant import (
    get_states,
    resolve_entity,
)

logger = logging.getLogger(__name__)


class ServiceRequest(BaseModel):
    domain: str
    service: str
    data: dict | None = None


router = APIRouter(tags=["home-assistant"])


@router.get("/ha/entities")
async def ha_entities(user_id: str = Depends(get_current_user_id)):
    try:
        return await get_states()
    except Exception as e:
        logger.exception("HA states error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


@router.post("/ha/service")
async def ha_service(
    req: ServiceRequest,
    _nonce: None = Depends(require_nonce),
    user_id: str = Depends(get_current_user_id),
):
    try:
        # dynamic import ensures monkeypatch works in tests
        from app import home_assistant as _ha

        resp = await _ha.call_service(req.domain, req.service, req.data or {})
        return resp or {"status": "ok"}
    except Exception as e:
        logger.exception("HA service error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


class WebhookAck(BaseModel):
    status: str = "ok"


@router.post("/ha/webhook", response_model=WebhookAck)
async def ha_webhook(request: Request):
    from app.security import verify_webhook

    _ = await verify_webhook(request)
    return WebhookAck()


@router.get("/ha/resolve")
async def ha_resolve(name: str, user_id: str = Depends(get_current_user_id)):
    try:
        entity = await resolve_entity(name)
        if entity:
            return {"entity_id": entity}
        raise HTTPException(status_code=404, detail="Entity not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("HA resolve error: %s", e)
        raise HTTPException(status_code=500, detail="Home Assistant error")


