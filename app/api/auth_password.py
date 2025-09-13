from __future__ import annotations

from datetime import UTC

from fastapi import APIRouter, HTTPException
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.core import get_async_db
from app.db.models import AuthUser

router = APIRouter(tags=["auth"], include_in_schema=False)


_pwd = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")


@router.post("/auth/register_pw")
async def register_pw(body: dict[str, str]):
    u = (body.get("username") or "").strip().lower()
    p = body.get("password") or ""
    if not u or len(p) < 6:
        raise HTTPException(status_code=400, detail="invalid")
    h = _pwd.hash(p)

    # Create user with username and password
    from datetime import datetime

    user = AuthUser(
        username=u,
        email=f"{u}@local.auth",  # Generate a dummy email for username-based auth
        password_hash=h,
        name=u,  # Use username as display name
        created_at=datetime.now(UTC),
    )

    try:
        async with get_async_db() as session:
            session.add(user)
            await session.commit()
    except IntegrityError:
        raise HTTPException(status_code=400, detail="username_taken")

    return {"status": "ok"}


@router.post("/auth/login_pw")
async def login_pw(body: dict[str, str]):
    u = (body.get("username") or "").strip().lower()
    p = body.get("password") or ""

    # Find user by username
    async with get_async_db() as session:
        stmt = select(AuthUser.password_hash).where(AuthUser.username == u)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()

    if not row:
        from ..http_errors import unauthorized

        raise unauthorized(
            code="invalid_credentials",
            message="invalid credentials",
            hint="check username/password",
        )

    if not _pwd.verify(p, row):
        from ..http_errors import unauthorized

        raise unauthorized(
            code="invalid_credentials",
            message="invalid credentials",
            hint="check username/password",
        )

    return {"status": "ok"}


__all__ = ["router"]
