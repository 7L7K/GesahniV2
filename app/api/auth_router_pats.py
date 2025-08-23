from fastapi import APIRouter, Depends, Request

router = APIRouter()

from .auth import list_pats as _list_pats_impl
from .auth import create_pat as _create_pat_impl
from .auth import _get_pat_by_id as _get_pat_by_id_impl
from .auth import revoke_pat as _revoke_pat_impl
from .deps.user import get_current_user_id


@router.get("/pats")
async def list_pats(user_id: str = Depends(get_current_user_id)):
    return await _list_pats_impl(user_id)


@router.post("/pats")
async def create_pat(body: dict, user_id: str = Depends(get_current_user_id)):
    return await _create_pat_impl(body, user_id)


@router.delete("/pats/{pat_id}")
async def revoke_pat(pat_id: str, user_id: str = Depends(get_current_user_id)):
    return await _revoke_pat_impl(pat_id, user_id)
