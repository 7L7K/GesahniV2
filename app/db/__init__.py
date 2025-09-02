# Database utilities and path resolution
from __future__ import annotations
import asyncio
import os
import logging

_logger = logging.getLogger(__name__)

_INIT_DONE = False

async def init_all_tables() -> None:
    """Initialize ALL database tables across the entire application.

    This function guarantees that every store module has its tables created
    before any tests or application code touches the databases.

    Called once per test session to prevent sqlite3.OperationalError: no such table.
    """
    global _INIT_DONE
    if _INIT_DONE:
        _logger.debug("init_all_tables: already initialized, skipping")
        return

    _logger.info("init_all_tables: initializing all database tables...")

    # 1. Auth store (users, sessions, etc.)
    from app.auth_store import ensure_tables as auth_ensure
    await auth_ensure()

    # 2. Care store (care-related data)
    from app.care_store import ensure_tables as care_ensure
    await care_ensure()

    # 3. Music store (music tokens and devices)
    from app.music.store import _ensure_tables as music_token_ensure
    await music_token_ensure()

    # 4. Third-party tokens store (OAuth tokens)
    from app.auth_store_tokens import TokenDAO
    token_dao = TokenDAO()
    await token_dao._ensure_table()

    # 5. Music token store (Spotify, etc.)
    from app.music.token_store import TokenStore as MusicTokenStore
    music_token_store = MusicTokenStore()
    await music_token_store._ensure_table()

    # 6. Auth module tables (password auth)
    from app.auth import _ensure_table as auth_table_ensure
    await auth_table_ensure()

    _INIT_DONE = True
    _logger.info("init_all_tables: all database tables initialized successfully")

# Backwards compatibility - keep the old functions
async def init_db_once_async() -> None:
    """Initialize all database tables asynchronously."""
    await init_all_tables()

async def init_db_once():
    """Initialize all database tables asynchronously."""
    await init_all_tables()

# optional back-compat for older tests
def bootstrap_databases_once():
    return init_db_once()
