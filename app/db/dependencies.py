"""
FastAPI database dependencies
"""
from collections.abc import AsyncGenerator, Generator
from contextlib import suppress

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from .config import (
    create_async_engine,
    create_sync_engine,
    get_async_session_factory,
    get_session_factory,
)

# Global engine instances (create once)
sync_engine = create_sync_engine()
async_engine = create_async_engine()

# Session factories
SyncSessionLocal = get_session_factory(sync_engine)
AsyncSessionLocal = get_async_session_factory(async_engine)


# Synchronous dependency
def get_db() -> Generator[Session, None, None]:
    """Synchronous database session dependency for FastAPI"""
    with SyncSessionLocal() as session:
        try:
            yield session
        finally:
            session.close()


# Asynchronous dependency
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Asynchronous database session dependency for FastAPI"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# --- begin addition: async engine disposer registry ---
_async_engines: list = []

# Best-effort registrations for known engine variables
try:  # noqa: F821
    _async_engines.append(async_engine)  # type: ignore[name-defined]
except Exception:
    pass

# Some codebases use a generic name `engine` for async engine; try to register
try:  # noqa: F821
    if 'engine' in globals():
        _async_engines.append(globals()['engine'])
except Exception:
    pass


async def dispose_engines() -> None:
    """Dispose all known SQLAlchemy async engines (best-effort)."""
    for e in list(_async_engines):
        with suppress(Exception):
            await e.dispose()
# --- end addition ---


# Example usage in FastAPI routes:
"""
from fastapi import Depends, APIRouter
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.dependencies import get_db, get_async_db

router = APIRouter()

# Synchronous route
@router.get("/users/sync")
def get_users_sync(db: Session = Depends(get_db)):
    # Use db session here
    return {"users": []}

# Asynchronous route
@router.get("/users/async")
async def get_users_async(db: AsyncSession = Depends(get_async_db)):
    # Use async db session here
    return {"users": []}
"""
