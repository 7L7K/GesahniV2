"""
Database package initialization
"""
from .config import (
    create_sync_engine,
    create_async_engine,
    get_session_factory,
    get_async_session_factory,
    health_check
)

__all__ = [
    "create_sync_engine",
    "create_async_engine",
    "get_session_factory",
    "get_async_session_factory",
    "health_check",
]


async def init_db_once() -> None:
    """Best-effort initialization of lightweight SQLite-backed stores for tests.

    The production application may use Alembic migrations; for tests we
    ensure the minimal tables exist so endpoints don't fail at import-time.
    """
    try:
        from app.auth_store import ensure_tables as _ensure_auth
        await _ensure_auth()
    except Exception:
        pass
    try:
        from app.auth_store_tokens import TokenDAO
        dao = TokenDAO(str(getattr(TokenDAO, "DEFAULT_DB_PATH", "third_party_tokens.db")))
        await dao._ensure_table()
    except Exception:
        pass
    try:
        from app.care_store import ensure_tables as _ensure_care
        await _ensure_care()
    except Exception:
        pass
    try:
        from app.music.store import _ensure_tables as _ensure_music
        await _ensure_music()
    except Exception:
        pass
