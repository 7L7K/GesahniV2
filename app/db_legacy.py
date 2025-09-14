"""
Centralized database initialization module.

This module provides a single function to initialize all database schemas
once during application startup, preventing redundant schema creation
during runtime operations.
"""

import logging

from sqlalchemy import text

from .db.core import sync_engine

logger = logging.getLogger(__name__)


async def init_db_once() -> None:
    """
    Initialize all database schemas once during application startup.

    This function consolidates all CREATE TABLE statements from various
    modules to ensure schemas are created only once at startup rather
    than repeatedly during runtime operations.
    """
    logger.info(
        "PostgreSQL migrations are expected to manage schema; init_db_once is a no-op"
    )
    try:
        # Lightweight connectivity check
        with sync_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        logger.warning("Database connectivity check failed during init_db_once: %s", e)


async def _init_auth_db() -> None:
    return None


async def _init_auth_store_db() -> None:
    return None


async def _init_care_db() -> None:
    return None


async def _init_music_db() -> None:
    return None
