from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import ConfigDict

from app.deps.user import get_current_user_id
from app.models.common import OkResponse as CommonOkResponse

router = APIRouter(tags=["TV"])


PHOTOS_DIR = Path(os.getenv("PHOTOS_DIR", "data/photos"))
PUBLIC_PREFIX = "/static/photos"
FAVS_FILE = Path(os.getenv("FAVORITES_FILE", "data/favorites.json"))


def _list_images() -> list[str]:
    if not PHOTOS_DIR.exists():
        return []
    out: list[str] = []
    for p in sorted(PHOTOS_DIR.iterdir()):
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"} and p.is_file():
            out.append(p.name)
    return out


def _read_favs() -> set[str]:
    try:
        import json

        if FAVS_FILE.exists():
            data = json.loads(FAVS_FILE.read_text(encoding="utf-8") or "[]")
            return set(x for x in data if isinstance(x, str))
    except Exception:
        pass
    return set()


def _write_favs(items: set[str]) -> None:
    try:
        import json

        FAVS_FILE.parent.mkdir(parents=True, exist_ok=True)
        FAVS_FILE.write_text(
            json.dumps(sorted(items), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass


@router.get("/tv/photos")
async def list_photos(user_id: str = Depends(get_current_user_id)):
    images = _list_images()
    favs = _read_favs()
    # Return web-accessible folder path mounted in app.main
    return {"folder": PUBLIC_PREFIX, "items": images, "favorites": sorted(favs)}


@router.post("/tv/photos/favorite")
class TvPhotoOkResponse(CommonOkResponse):
    model_config = ConfigDict(title="OkResponse")


@router.post(
    "/tv/photos/favorite",
    response_model=TvPhotoOkResponse,
    responses={200: {"model": TvPhotoOkResponse}},
)
async def mark_favorite(
    body: dict | None = None,
    name: str | None = None,
    user_id: str = Depends(get_current_user_id),
):
    # Prefer JSON body { name }, fall back to query param for backward compat
    if body and isinstance(body, dict) and not name:
        name = str(body.get("name") or "")
    name = (name or "").strip()
    images = set(_list_images())
    if name and name in images:
        favs = _read_favs()
        favs.add(name)
        _write_favs(favs)
        return {"status": "ok"}
    return {"status": "ignored"}
