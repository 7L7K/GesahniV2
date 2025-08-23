from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.models.common import OkResponse as CommonOkResponse

from ..deps.user import get_current_user_id
from .music import music_command

router = APIRouter(tags=["TV"], prefix="")


class DuckBody(BaseModel):
    level: int = 15

    model_config = ConfigDict(json_schema_extra={"example": {"level": 15}})


class OkResponse(CommonOkResponse):
    model_config = ConfigDict(title="OkResponse")


@router.post(
    "/ui/duck", response_model=OkResponse, responses={200: {"model": OkResponse}}
)
async def ui_duck(body: DuckBody, user_id: str = Depends(get_current_user_id)):
    # Simulate alert duck: temp cap with restore
    await music_command(type("_", (), {"command": "volume", "volume": body.level, "temporary": True})(), user_id)  # type: ignore[arg-type]
    return {"status": "ok"}


@router.post(
    "/ui/restore", response_model=OkResponse, responses={200: {"model": OkResponse}}
)
async def ui_restore(user_id: str = Depends(get_current_user_id)):
    from .music import restore_volume

    return await restore_volume(user_id)  # type: ignore[arg-type]
