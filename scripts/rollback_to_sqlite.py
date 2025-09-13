#!/usr/bin/env python3
"""
Emergency rollback script for GesahniV2 PostgreSQL migration.

This script temporarily restores SQLite support if PostgreSQL is unreachable.
Use only in emergency situations when PostgreSQL connectivity cannot be restored.

USAGE:
    python scripts/rollback_to_sqlite.py

This will:
1. Temporarily restore SQLite fallback in app/db/core.py
2. Set DATABASE_URL to SQLite default
3. Log emergency rollback action

⚠️  WARNING: This is a temporary emergency measure only!
   Restore PostgreSQL connectivity and re-enable PostgreSQL-only mode ASAP.
"""

import os
import sys
from pathlib import Path

def create_emergency_sqlite_core():
    """Create emergency SQLite-enabled version of core.py"""
    core_content = '''"""
EMERGENCY ROLLBACK MODE: SQLite fallback restored

⚠️  WARNING: This is a temporary emergency measure!
   PostgreSQL connectivity should be restored immediately.

This mode allows SQLite fallback when PostgreSQL is unreachable.
"""

import logging
import os
from collections.abc import AsyncGenerator, Generator

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

# EMERGENCY: Allow SQLite fallback
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./gesahni.db")

if DATABASE_URL.startswith("sqlite://"):
    logger.warning("🚨 EMERGENCY: Using SQLite fallback - restore PostgreSQL ASAP!")
elif not DATABASE_URL.startswith("postgresql://"):
    logger.warning("🚨 EMERGENCY: Invalid DATABASE_URL - using SQLite fallback")
    DATABASE_URL = "sqlite:///./gesahni.db"

# Synchronous engine configuration
if DATABASE_URL.startswith("sqlite://"):
    sync_engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
        echo=False,
        connect_args={"check_same_thread": False}
    )
else:
    sync_engine = create_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://"),
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
        echo=False,
    )

# Asynchronous engine configuration
if DATABASE_URL.startswith("sqlite://"):
    from sqlalchemy.pool import StaticPool
    async_engine = sa_create_async_engine(
        DATABASE_URL,
        future=True,
        echo=False,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False}
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

def get_db() -> Generator[Session, None, None]:
    """Synchronous database session dependency for FastAPI"""
    with SyncSessionLocal() as session:
        try:
            yield session
        finally:
            session.close()

async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Asynchronous database session dependency for FastAPI"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()

def health_check() -> bool:
    """Database connectivity check"""
    try:
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        return False

async def health_check_async() -> bool:
    """Asynchronous database connectivity check"""
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
    "health_check",
    "health_check_async",
    "dispose_engines",
]
'''

    core_path = Path(__file__).parent.parent / "app" / "db" / "core.py"
    backup_path = core_path.with_suffix('.py.backup')

    # Create backup of current core.py
    if core_path.exists():
        core_path.rename(backup_path)
        print(f"📁 Backed up original core.py to {backup_path}")

    # Write emergency version
    core_path.write_text(core_content)
    print(f"🚨 EMERGENCY: Created SQLite-enabled core.py at {core_path}")

def set_sqlite_env():
    """Set environment to use SQLite"""
    os.environ["DATABASE_URL"] = "sqlite:///./gesahni.db"
    print("🔧 Set DATABASE_URL to SQLite fallback")

def main():
    """Main rollback function"""
    print("🚨 EMERGENCY ROLLBACK: Enabling SQLite fallback mode")
    print("=" * 60)

    try:
        create_emergency_sqlite_core()
        set_sqlite_env()

        print("\n✅ EMERGENCY ROLLBACK COMPLETE")
        print("\n⚠️  IMPORTANT NEXT STEPS:")
        print("1. Restart the application")
        print("2. Restore PostgreSQL connectivity")
        print("3. Run: python scripts/restore_postgres_mode.py")
        print("4. Verify application functionality")

    except Exception as e:
        print(f"❌ Rollback failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
