"""
Database session management helpers.

This module provides context managers for proper async session lifecycle management.
Always use these helpers instead of manually managing AsyncSession instances.
"""

from contextlib import asynccontextmanager
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession


@asynccontextmanager
async def session_scope(Session: Callable[[], AsyncSession]):
    """
    Context manager for proper AsyncSession lifecycle management.

    Ensures sessions are always committed on success and rolled back on exception,
    and always closed regardless of outcome.

    Args:
        Session: A callable that returns an AsyncSession (typically sessionmaker)

    Usage:
        from app.db.session import session_scope
        from app.db.core import AsyncSessionLocal

        async def my_function():
            async with session_scope(AsyncSessionLocal) as session:
                # Use session here - it will be committed on success
                # and rolled back on exception, then always closed
                result = await session.execute(...)
                return result.scalar_one()
    """
    session: AsyncSession | None = None
    try:
        session = Session()
        yield session
        await session.commit()
    except Exception:
        if session:
            await session.rollback()
        raise
    finally:
        if session:
            await session.close()


@asynccontextmanager
async def get_session_context(Session: Callable[[], AsyncSession]):
    """
    Alternative name for session_scope for backward compatibility.

    DEPRECATED: Use session_scope instead.
    """
    async with session_scope(Session) as session:
        yield session


__all__ = ["session_scope", "get_session_context"]

