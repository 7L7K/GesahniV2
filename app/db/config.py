"""
PostgreSQL-only DB configuration for GesahniV2.

This module intentionally enforces PostgreSQL and removes any SQLite fallbacks.
Use app.db.core for engines and dependencies in application code.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine
from sqlalchemy.orm import sessionmaker


def _require_pg_url() -> str:
    url = os.getenv("DATABASE_URL", "postgresql://app:app_pw@localhost:5432/gesahni")
    if not url.startswith("postgresql://"):
        raise RuntimeError("DATABASE_URL must be a PostgreSQL URL (postgresql://...)")
    return url


def get_database_url(async_mode: bool = False) -> str:
    base_url = _require_pg_url()
    if async_mode:
        return base_url.replace("postgresql://", "postgresql+asyncpg://")
    return base_url.replace("postgresql://", "postgresql+psycopg2://")


def create_sync_engine():
    db_url = get_database_url(async_mode=False)
    return create_engine(
        db_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800,
        future=True,
        echo=False,
    )


def create_async_engine():
    db_url = get_database_url(async_mode=True)
    return sa_create_async_engine(db_url, future=True, echo=False)


def get_session_factory(engine):
    return sessionmaker(bind=engine, future=True)


def get_async_session_factory(engine):
    return async_sessionmaker(bind=engine, future=True)


def health_check(engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False
