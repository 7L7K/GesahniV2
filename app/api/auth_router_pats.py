import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from ..auth_protection import require_auth_with_csrf
from ..auth_store import create_pat as _create_pat_impl
from ..auth_store import get_pat_by_id as _get_pat_by_id
from ..auth_store import list_pats_for_user as _list_pats_for_user
from ..auth_store import revoke_pat as _revoke_pat
from ..deps.user import get_current_user_id
from ..http_errors import unauthorized

router = APIRouter(tags=["Auth"])  # Mounted under /v1 by routers.config
legacy_router = APIRouter(tags=["Auth"], prefix="/auth", include_in_schema=False)


@router.get("/pats")
async def list_pats(
    user_id: str = Depends(get_current_user_id),
) -> dict[str, list[dict[str, Any]]]:
    if user_id == "anon":
        raise unauthorized(
            message="authentication required",
            hint="login or include Authorization header",
        )
    try:
        pats = await _list_pats_for_user(user_id)
        return {"items": pats}
    except Exception as exc:
        # Gracefully degrade if DB is not ready or schema is missing
        logging.getLogger(__name__).warning(
            "pats_list_failed", extra={"user_id": user_id, "error": str(exc)}
        )
        return {"items": []}


@router.post("/pats")
async def create_pat(body: dict, user_id: str = Depends(require_auth_with_csrf)):
    return await _create_pat_impl(body, user_id)


@router.delete("/pats/{pat_id}")
async def revoke_pat(
    pat_id: str, user_id: str = Depends(require_auth_with_csrf)
) -> dict[str, str]:
    pat = await _get_pat_by_id(pat_id)
    if not pat or pat.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="pat_not_found")
    await _revoke_pat(pat_id)
    return {"status": "revoked", "pat_id": pat_id}


@legacy_router.get("/pats", include_in_schema=False)
async def legacy_list() -> RedirectResponse:
    return RedirectResponse(url="/v1/pats", status_code=308)


@legacy_router.post("/pats", include_in_schema=False)
async def legacy_create() -> RedirectResponse:
    return RedirectResponse(url="/v1/pats", status_code=308)


@legacy_router.delete("/pats/{pat_id}", include_in_schema=False)
async def legacy_revoke(pat_id: str) -> RedirectResponse:
    return RedirectResponse(url="/v1/pats", status_code=308)


__all__ = ["router", "legacy_router"]
