from fastapi import APIRouter

from .debug import router as debug_router
from .login import router as login_router
from .logout import router as logout_router
from .refresh import router as refresh_router
from .register import router as register_router
from .token import router as token_router

router = APIRouter(tags=["Auth"])
router.include_router(login_router)
router.include_router(register_router)
router.include_router(refresh_router)
router.include_router(logout_router)
router.include_router(token_router)
router.include_router(debug_router)
