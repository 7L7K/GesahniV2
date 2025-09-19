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
logger.info("🗄️ DB_SYNC_ENGINE_INIT", extra={
    "pool_size": 10,
    "max_overflow": 20,
    "pool_pre_ping": True,
    "pool_recycle": 1800,
    "pool_timeout": 30,
    "timestamp": __import__('time').time(),
})

sync_engine = create_engine(
    DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://"),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=1800,
    pool_timeout=30,
    future=True,
    echo=False,
)

# Asynchronous engine configuration (test-aware pool)
if os.getenv("DB_POOL", "enabled") == "disabled":
    logger.info("🗄️ DB_ASYNC_ENGINE_INIT", extra={
        "pool_disabled": True,
        "pool_class": "NullPool",
        "timestamp": __import__('time').time(),
    })
    async_engine = sa_create_async_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        poolclass=NullPool,
        future=True,
        echo=False,
    )
else:
    logger.info("🗄️ DB_ASYNC_ENGINE_INIT", extra={
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 1800,
        "pool_timeout": 30,
        "timestamp": __import__('time').time(),
    })
    async_engine = sa_create_async_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_timeout=30,
        pool_reset_on_return="commit",  # Reset connections on return to prevent stale transactions
        future=True,
        echo=False,
    )

# Session factories
SyncSessionLocal = sessionmaker(bind=sync_engine, future=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, future=True)


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Yield an async SQLAlchemy session that always closes cleanly."""

    session = None
    start_time = __import__('time').time()

    try:
        session = AsyncSessionLocal()
        logger.debug("🗄️ DB_ASYNC_SESSION_CREATED", extra={
            "session_type": "async",
            "timestamp": start_time,
        })
        yield session
    except Exception as e:
        if session:
            try:
                await session.rollback()
                logger.warning("🗄️ DB_ASYNC_SESSION_ROLLBACK", extra={
                    "session_type": "async",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round((__import__('time').time() - start_time) * 1000, 2),
                    "timestamp": __import__('time').time(),
                })
            except Exception as rollback_error:
                logger.error("🗄️ DB_ASYNC_SESSION_ROLLBACK_FAILED", extra={
                    "session_type": "async",
                    "original_error": str(e),
                    "rollback_error": str(rollback_error),
                    "timestamp": __import__('time').time(),
                })
        raise
    finally:
        if session:
            try:
                await session.close()
                logger.debug("🗄️ DB_ASYNC_SESSION_CLOSED", extra={
                    "session_type": "async",
                    "duration_ms": round((__import__('time').time() - start_time) * 1000, 2),
                    "timestamp": __import__('time').time(),
                })
            except Exception as close_error:
                logger.error("🗄️ DB_ASYNC_SESSION_CLOSE_FAILED", extra={
                    "session_type": "async",
                    "close_error": str(close_error),
                    "timestamp": __import__('time').time(),
                })


def get_db() -> Generator[Session, None, None]:
    """Synchronous database session dependency for FastAPI"""
    start_time = __import__('time').time()
    with SyncSessionLocal() as session:
        logger.debug("🗄️ DB_SYNC_SESSION_CREATED", extra={
            "session_type": "sync",
            "timestamp": start_time,
        })
        try:
            yield session
        except Exception as e:
            logger.warning("🗄️ DB_SYNC_SESSION_ERROR", extra={
                "session_type": "sync",
                "error": str(e),
                "error_type": type(e).__name__,
                "duration_ms": round((__import__('time').time() - start_time) * 1000, 2),
                "timestamp": __import__('time').time(),
            })
            raise
        finally:
            session.close()
            logger.debug("🗄️ DB_SYNC_SESSION_CLOSED", extra={
                "session_type": "sync",
                "duration_ms": round((__import__('time').time() - start_time) * 1000, 2),
                "timestamp": __import__('time').time(),
            })


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
        session = None
        try:
            session = AsyncSessionLocal()
            yield session
        finally:
            if session:
                await session.close()

    # Context manager support
    async def __aenter__(self):
        if self._generator is None:
            self._generator = self._create_generator()
        self._session = await anext(self._generator)
        return self._session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass  # Best effort cleanup
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
