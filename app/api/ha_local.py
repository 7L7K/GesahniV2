from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.api._deps import dep_nonce, deps_ha_http
from app.deps.flags import require_home_assistant
from app.deps.user import get_current_user_id
from app.home_assistant import call_service, get_states, resolve_entity
from app.security.webhooks import verify_webhook

router = APIRouter(tags=["Care"], dependencies=deps_ha_http() + [Depends(require_home_assistant)])


class ServiceRequest(BaseModel):
    domain: str
    service: str
    data: dict | None = None
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "domain": "light",
                "service": "turn_on",
                "data": {"entity_id": "light.kitchen"},
            }
        }
    )


@router.get("/ha/entities")
async def ha_entities(user_id: str = Depends(get_current_user_id)):
    try:
        return await get_states()
    except Exception as e:
        raise HTTPException(status_code=500, detail="Home Assistant error") from e


@router.post("/ha/service")
async def ha_service(
    req: ServiceRequest,
    _nonce: None = dep_nonce(),
    user_id: str = Depends(get_current_user_id),
):
    try:
        resp = await call_service(req.domain, req.service, req.data or {})
        return resp or {"status": "ok"}
    except Exception:
        # In tests you can relax this if needed
        raise HTTPException(status_code=400, detail="Home Assistant error")


@router.post("/ha/webhook")
async def ha_webhook(request: Request):
    _ = await verify_webhook(request)
    return {"status": "ok"}


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
        raise HTTPException(status_code=500, detail="Home Assistant error") from e


# Aliases (nickname table)
from app.alias_store import delete as alias_delete
from app.alias_store import get_all as alias_all
from app.alias_store import set as alias_set


@router.get("/ha/aliases")
async def list_aliases(user_id: str = Depends(get_current_user_id)):
    return await alias_all()


class AliasBody(BaseModel):
    name: str
    entity_id: str
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"name": "kitchen light", "entity_id": "light.kitchen"}
        }
    )


@router.post("/ha/aliases")
async def create_alias(body: AliasBody, user_id: str = Depends(get_current_user_id)):
    await alias_set(body.name, body.entity_id)
    return {"status": "ok"}


@router.delete("/ha/aliases")
async def delete_alias(name: str, user_id: str = Depends(get_current_user_id)):
    await alias_delete(name)
    return {"status": "ok"}
