import asyncio
import os
import sqlite3
import tempfile

import pytest

from app.auth_store_tokens import TokenDAO
from app.models.third_party_tokens import ThirdPartyToken


def create_legacy_db(path: str):
    """Create a legacy third_party_tokens table without the new encrypted columns."""
    with sqlite3.connect(path) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS third_party_tokens (
              id            TEXT PRIMARY KEY,
              user_id       TEXT NOT NULL,
              provider      TEXT NOT NULL,
              access_token  TEXT NOT NULL,
              refresh_token TEXT,
              scope         TEXT,
              expires_at    INTEGER NOT NULL,
              created_at    INTEGER NOT NULL,
              updated_at    INTEGER NOT NULL,
              is_valid      INTEGER DEFAULT 1
            )
        """)
        conn.commit()


@pytest.mark.asyncio
async def test_migration_applies_and_upserts(tmp_path):
    db_file = tmp_path / "legacy_tokens.db"
    create_legacy_db(str(db_file))

    dao = TokenDAO(db_path=str(db_file))

    token = ThirdPartyToken(
        user_id="testuser",
        provider="google",
        access_token="at_123",
        refresh_token="rt_456",
        scopes="openid email",
        expires_at=9999999999,
        created_at=1,
        updated_at=1,
    )

    # Should return True, applying migration and inserting
    ok = await dao.upsert_token(token)
    assert ok is True

    # Verify the new column exists and row is present
    with sqlite3.connect(str(db_file)) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(third_party_tokens)")
        cols = {r[1] for r in cur.fetchall()}
        assert "access_token_enc" in cols

        cur.execute("SELECT user_id, provider, access_token FROM third_party_tokens WHERE user_id = ?", ("testuser",))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "testuser"


