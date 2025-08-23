from fastapi import APIRouter, Depends

from app.deps.scopes import docs_security_with, optional_require_any_scope
from app.security import verify_token

try:
    from .music import router as _music_router
except Exception:
    _music_router = None

music_http = APIRouter(
    dependencies=[
        Depends(verify_token),
        Depends(optional_require_any_scope(["music:control"])),
        Depends(docs_security_with(["music:control"])),
    ]
)

if _music_router is not None:
    music_http.include_router(_music_router)
