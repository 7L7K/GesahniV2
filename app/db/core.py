"""
Single database core module for GesahniV2.

This module provides the only valid import path for database engines and sessions.
All database access must go through this module to ensure PostgreSQL-only consistency.

Imports from this module:
- sync_engine: Synchronous SQLAlchemy engine
- async_engine: Asynchronous SQLAlchemy engine
- get_db(): Synchronous FastAPI dependency
- get_async_db(): Asynchronous FastAPI dependency
- health_check(): Database connectivity verification
"""

import logging
import os
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Enforce PostgreSQL-only - no legacy file-backed store fallbacks
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is required (PostgreSQL-only)"
    )
if DATABASE_URL.split(":", 1)[0].lower() == "sqlite":
    raise RuntimeError("Legacy datastore path hit — not allowed in Postgres-only mode")

# Validate PostgreSQL URL format
if not DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith(
    "postgresql+"
):
    raise RuntimeError(
        "DATABASE_URL must be a PostgreSQL URL (postgresql://... or postgresql+driver://...)"
    )

# Synchronous engine configuration
sync_engine = create_engine(
    DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://"),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
    future=True,
    echo=False,
)

# Asynchronous engine configuration (test-aware pool)
if os.getenv("DB_POOL", "enabled") == "disabled":
    async_engine = sa_create_async_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        poolclass=NullPool,
        future=True,
        echo=False,
    )
else:
    async_engine = sa_create_async_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
        echo=False,
    )

# Session factories
SyncSessionLocal = sessionmaker(bind=sync_engine, future=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, future=True)


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Yield an async SQLAlchemy session that always closes cleanly."""

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


def get_db() -> Generator[Session, None, None]:
    """Synchronous database session dependency for FastAPI"""
    with SyncSessionLocal() as session:
        try:
            yield session
        finally:
            session.close()


class AsyncSessionGenerator:
    """Async generator that also supports context manager protocol."""

    def __init__(self):
        self._generator = None
        self._session = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._generator is None:
            self._generator = self._create_generator()
        try:
            self._session = await anext(self._generator)
            return self._session
        except StopAsyncIteration:
            raise

    async def _create_generator(self):
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()

    # Context manager support
    async def __aenter__(self):
        if self._generator is None:
            self._generator = self._create_generator()
        self._session = await anext(self._generator)
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            await self._session.close()
        self._session = None


def get_async_db() -> AsyncSessionGenerator:
    """
    Asynchronous database session dependency for FastAPI.

    Can be used as:
    - async for session in get_async_db():  # Generator usage
    - async with get_async_db() as session:  # Context manager usage
    """
    return AsyncSessionGenerator()


def health_check() -> bool:
    """PostgreSQL connectivity check"""
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        return False


async def health_check_async() -> bool:
    """Asynchronous PostgreSQL connectivity check"""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Async database health check failed: %s", e)
        return False


async def dispose_engines() -> None:
    """Dispose SQLAlchemy engines on shutdown"""
    await async_engine.dispose()


__all__ = [
    "sync_engine",
    "async_engine",
    "get_db",
    "get_async_db",
    "get_async_session",
    "health_check",
    "health_check_async",
    "dispose_engines",
]
