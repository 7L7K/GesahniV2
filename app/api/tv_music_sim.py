from __future__ import annotations

import asyncio
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..deps.user import get_current_user_id
from .music import music_command


router = APIRouter(tags=["music"], prefix="")


class DuckBody(BaseModel):
    level: int = 15


@router.post("/ui/duck")
async def ui_duck(body: DuckBody, user_id: str = Depends(get_current_user_id)):
    # Simulate alert duck: temp cap with restore
    await music_command(type("_", (), {"command": "volume", "volume": body.level, "temporary": True})(), user_id)  # type: ignore[arg-type]
    return {"status": "ok"}


@router.post("/ui/restore")
async def ui_restore(user_id: str = Depends(get_current_user_id)):
    from .music import restore_volume

    return await restore_volume(user_id)  # type: ignore[arg-type]


