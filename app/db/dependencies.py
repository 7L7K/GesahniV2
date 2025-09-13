"""
FastAPI database dependencies - DEPRECATED

⚠️  DEPRECATED: This module is deprecated. Import from app.db.core instead.

All database access should now use:
from app.db.core import get_db, get_async_db, sync_engine, async_engine

This file remains for backward compatibility during migration.
"""

import warnings
from collections.abc import AsyncGenerator, Generator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

# Re-export from the new core module
from .core import (  # noqa: F401
    AsyncSessionLocal,
    SyncSessionLocal,
    async_engine,
    dispose_engines,
    get_async_db,
    get_db,
    sync_engine,
)

warnings.warn(
    "app.db.dependencies is deprecated. Import from app.db.core instead.",
    DeprecationWarning,
    stacklevel=2
)


# Legacy functions - redirect to core module
def get_db() -> Generator[Session, None, None]:  # type: ignore
    """DEPRECATED: Use app.db.core.get_db instead"""
    warnings.warn("get_db is deprecated. Import from app.db.core", DeprecationWarning, stacklevel=2)
    from .core import get_db as _get_db
    yield from _get_db()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:  # type: ignore
    """DEPRECATED: Use app.db.core.get_async_db instead"""
    warnings.warn("get_async_db is deprecated. Import from app.db.core", DeprecationWarning, stacklevel=2)
    from .core import get_async_db as _get_async_db
    async for session in _get_async_db():
        yield session


# Example usage in FastAPI routes (DEPRECATED - use app.db.core):
"""
# DEPRECATED - Use this instead:
from app.db.core import get_db, get_async_db

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
