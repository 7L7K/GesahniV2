"""
Database configuration for GesahniV2
"""
import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import async_sessionmaker


# Database URL configuration
def get_database_url(async_mode: bool = False) -> str:
    """Get database URL with optional async driver"""
    base_url = os.getenv("DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni")

    if async_mode:
        # Convert to asyncpg format
        return base_url.replace("postgresql://", "postgresql+asyncpg://")
    else:
        # Use psycopg2 for sync operations
        return base_url.replace("postgresql://", "postgresql+psycopg2://")


# Synchronous engine configuration
def create_sync_engine():
    """Create synchronous SQLAlchemy engine with production settings"""
    db_url = get_database_url(async_mode=False)

    return create_engine(
        db_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=1800,   # Recycle connections every 30 minutes
        future=True,
        echo=False,  # Set to True for SQL debugging
    )


# Asynchronous engine configuration
def create_async_engine():
    """Create asynchronous SQLAlchemy engine with production settings"""
    db_url = get_database_url(async_mode=True)

    return create_async_engine(
        db_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=1800,   # Recycle connections every 30 minutes
        echo=False,  # Set to True for SQL debugging
    )


# Session factories
def get_session_factory(engine):
    """Create session factory for synchronous operations"""
    return sessionmaker(bind=engine, future=True)


def get_async_session_factory(engine):
    """Create async session factory for asynchronous operations"""
    return async_sessionmaker(bind=engine, future=True)


# Database health check
def health_check(engine) -> bool:
    """Simple database connectivity check"""
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


# Example usage:
"""
# Synchronous usage
from app.db.config import create_sync_engine, get_session_factory

engine = create_sync_engine()
SessionLocal = get_session_factory(engine)

# In FastAPI dependency
def get_db():
    with SessionLocal() as session:
        yield session

# Asynchronous usage
from app.db.config import create_async_engine, get_async_session_factory

engine = create_async_engine()
AsyncSessionLocal = get_async_session_factory(engine)

# In FastAPI async dependency
async def get_async_db():
    async with AsyncSessionLocal() as session:
        yield session
"""
