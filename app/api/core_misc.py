from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.api._deps import deps_protected_http
from app.deps.user import get_current_user_id

router = APIRouter(tags=["Admin"], dependencies=deps_protected_http())


class AskRequest(BaseModel):
    # Accept both legacy text and chat-style array
    prompt: str | list[dict]
    model_override: str | None = Field(None, alias="model")
    stream: bool | None = Field(
        False, description="Force SSE when true; otherwise negotiated via Accept"
    )
    model_config = ConfigDict(
        title="AskRequest",
        validate_by_name=True,
        validate_by_alias=True,
        json_schema_extra={"example": {"prompt": "hello"}},
    )


@router.post("/intent-test", summary="No-op intent echo")
async def intent_test(req: AskRequest, user_id: str = Depends(get_current_user_id)):
    import logging

    logging.getLogger(__name__).info(
        "intent.test", extra={"meta": {"prompt": req.prompt}}
    )
    return {"intent": "test", "prompt": req.prompt}


@router.get("/client-crypto-policy")
async def client_crypto_policy() -> dict:
    return {
        "cipher": "AES-GCM-256",
        "key_wrap_methods": ["webauthn", "pbkdf2"],
        "storage": "indexeddb",
        "deks": "per-user-per-device",
    }


@router.get("/explain_route")
async def explain_route(req_id: str, user_id: str = Depends(get_current_user_id)):
    from app.history import get_record_by_req_id

    record = await get_record_by_req_id(req_id)
    if not record:
        raise HTTPException(status_code=404, detail="request_not_found")

    parts: list[str] = []
    skill = record.get("matched_skill") or None
    if skill:
        parts.append(f"skill={skill}")
    ha_call = record.get("ha_service_called")
    if ha_call:
        ents = record.get("entity_ids") or []
        parts.append(f"ha={ha_call}{(' ' + ','.join(ents)) if ents else ''}")
    if record.get("cache_hit"):
        parts.append("cache=hit")
    reason = record.get("route_reason") or None
    model = record.get("model_name") or None
    engine = record.get("engine_used") or None
    if reason:
        parts.append(f"route={reason}")
    if engine:
        parts.append(f"engine={engine}")
    if model:
        parts.append(f"model={model}")
    sc = record.get("self_check_score")
    if sc is not None:
        try:
            parts.append(f"self_check={float(sc):.2f}")
        except Exception:
            parts.append(f"self_check={sc}")
    if record.get("escalated"):
        parts.append("escalated=true")
    lat = record.get("latency_ms")
    if isinstance(lat, int):
        parts.append(f"latency={lat}ms")

    return {
        "req_id": req_id,
        "breadcrumb": " | ".join(parts),
        "meta": record.get("meta"),
    }
