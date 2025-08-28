from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from typing import Optional

from .models.third_party_tokens import ThirdPartyToken, TokenQuery, TokenUpdate
from .crypto_tokens import encrypt_token, decrypt_token

logger = logging.getLogger(__name__)

# Database configuration
DEFAULT_DB_PATH = os.getenv("THIRD_PARTY_TOKENS_DB", "third_party_tokens.db")


class TokenDAO:
    """Data Access Object for third-party tokens using SQLite."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def _ensure_table(self) -> None:
        """Ensure the third_party_tokens table exists."""
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                try:
                    logger.info(
                        "🔐 TOKEN STORE: ensuring table",
                        extra={"meta": {"db_path": self.db_path}},
                    )
                except Exception:
                    pass

                # Create table if it doesn't exist (with the full modern schema)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS third_party_tokens (
                        id                     TEXT PRIMARY KEY,
                        user_id                TEXT NOT NULL,
                        provider               TEXT NOT NULL,
                        access_token           TEXT NOT NULL,
                        access_token_enc       BLOB,
                        refresh_token          TEXT,
                        refresh_token_enc      BLOB,
                        envelope_key_version   INTEGER DEFAULT 1,
                        last_refresh_at        INTEGER DEFAULT 0,
                        refresh_error_count    INTEGER DEFAULT 0,
                        scope                  TEXT,
                        expires_at             INTEGER NOT NULL,
                        created_at             INTEGER NOT NULL,
                        updated_at             INTEGER NOT NULL,
                        is_valid               INTEGER DEFAULT 1
                    )
                    """
                )

                # Backfill missing columns for older databases
                try:
                    cursor.execute("PRAGMA table_info(third_party_tokens)")
                    cols = {row[1] for row in cursor.fetchall()}
                except Exception:
                    cols = set()

                # Define required columns and their SQL definitions for ALTER
                required_cols = {
                    "access_token_enc": "BLOB",
                    "refresh_token_enc": "BLOB",
                    "envelope_key_version": "INTEGER DEFAULT 1",
                    "last_refresh_at": "INTEGER DEFAULT 0",
                    "refresh_error_count": "INTEGER DEFAULT 0",
                }

                for col, col_type in required_cols.items():
                    if col not in cols:
                        try:
                            cursor.execute(
                                f"ALTER TABLE third_party_tokens ADD COLUMN {col} {col_type}"
                            )
                        except Exception:
                            # Ignore if concurrent migrations or SQLite limitations
                            pass

                # Create indexes
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tokens_user_provider
                    ON third_party_tokens (user_id, provider)
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tokens_expires_at
                    ON third_party_tokens (expires_at)
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tokens_provider
                    ON third_party_tokens (provider)
                """)

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_tokens_valid
                    ON third_party_tokens (is_valid)
                """)

                # Unique constraint for valid tokens
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_tokens_user_provider_unique
                    ON third_party_tokens (user_id, provider)
                    WHERE is_valid = 1
                """)

                conn.commit()

    async def upsert_token(self, token: ThirdPartyToken) -> bool:
        """
        Insert or update a token.

        Args:
            token: The token to upsert

        Returns:
            True if successful, False otherwise
        """
        logger.info("🔐 TOKEN STORE: Upserting token", extra={
            "meta": {
                "token_id": token.id,
                "user_id": token.user_id,
                "provider": token.provider,
                "has_access_token": bool(token.access_token),
                "has_refresh_token": bool(token.refresh_token),
                "access_token_length": len(token.access_token) if token.access_token else 0,
                "refresh_token_length": len(token.refresh_token) if token.refresh_token else 0,
                "expires_at": token.expires_at,
                "scope": token.scope
            }
        })

        try:
            await self._ensure_table()

            async with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Mark existing valid tokens for this user/provider as invalid
                    cursor.execute("""
                        UPDATE third_party_tokens
                        SET is_valid = 0, updated_at = ?
                        WHERE user_id = ? AND provider = ? AND is_valid = 1
                    """, (token.updated_at, token.user_id, token.provider))

                    # If refresh_token present, encrypt and store into refresh_token_enc
                    refresh_token_enc = None
                    envelope_key_version = 1
                    last_refresh_at = 0
                    refresh_error_count = 0
                    # Encrypt refresh_token and access_token when provided
                    access_token_enc = None
                    if token.refresh_token:
                        try:
                            refresh_token_enc = encrypt_token(token.refresh_token)
                            last_refresh_at = int(__import__("time").time())
                        except Exception:
                            refresh_token_enc = None
                    if token.access_token:
                        try:
                            access_token_enc = encrypt_token(token.access_token)
                        except Exception:
                            access_token_enc = None
                    # Build insertion tuple matching ThirdPartyToken.to_db_tuple()
                    insert_tuple = (
                        token.id,
                        token.user_id,
                        token.provider,
                        token.access_token,
                        access_token_enc,
                        None if refresh_token_enc else token.refresh_token,
                        refresh_token_enc,
                        envelope_key_version,
                        last_refresh_at,
                        refresh_error_count,
                        token.scope,
                        token.expires_at,
                        token.created_at,
                        token.updated_at,
                        1 if token.is_valid else 0,
                    )

                    cursor.execute("""
                        INSERT INTO third_party_tokens
                        (id, user_id, provider, access_token, access_token_enc, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count,
                         scope, expires_at, created_at, updated_at, is_valid)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, insert_tuple)

                    conn.commit()

                    logger.info("🔐 TOKEN STORE: Token upserted successfully", extra={
                        "meta": {
                            "token_id": token.id,
                            "user_id": token.user_id,
                            "provider": token.provider,
                            "operation": "upsert_success",
                            "db_path": self.db_path,
                            "expires_at": token.expires_at,
                            "has_refresh_enc": bool(refresh_token_enc),
                        }
                    })

                    return True

        except Exception as e:
            logger.error("🔐 TOKEN STORE: Token upsert failed", extra={
                "meta": {
                    "token_id": token.id,
                    "user_id": token.user_id,
                    "provider": token.provider,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "operation": "upsert_failed"
                }
            })
            return False

    async def get_token(self, user_id: str, provider: str) -> Optional[ThirdPartyToken]:
        """
        Retrieve a valid token for the given user and provider.

        Args:
            user_id: User identifier
            provider: Provider name

        Returns:
            Token if found and valid, None otherwise
        """
        try:
            await self._ensure_table()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Select columns in the canonical order expected by ThirdPartyToken.from_db_row
                cursor.execute(
                    """
                    SELECT
                        id,
                        user_id,
                        provider,
                        access_token,
                        access_token_enc,
                        refresh_token,
                        refresh_token_enc,
                        envelope_key_version,
                        last_refresh_at,
                        refresh_error_count,
                        scope,
                        expires_at,
                        created_at,
                        updated_at,
                        is_valid
                    FROM third_party_tokens
                    WHERE user_id = ? AND provider = ? AND is_valid = 1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id, provider),
                )

                row = cursor.fetchone()
                if row:
                    t = ThirdPartyToken.from_db_row(row)
                    # If encrypted access or refresh token present, attempt decryption
                    try:
                        if t.refresh_token_enc:
                            from .crypto_tokens import decrypt_token

                            t.refresh_token = decrypt_token(t.refresh_token_enc)
                    except Exception:
                        # Decryption failed: keep plaintext column if present (rollback mode)
                        logger.warning("Failed to decrypt refresh_token_enc, falling back to plaintext column if available")
                    try:
                        if t.access_token_enc:
                            from .crypto_tokens import decrypt_token

                            t.access_token = decrypt_token(t.access_token_enc)
                    except Exception:
                        logger.warning("Failed to decrypt access_token_enc, falling back to plaintext access_token if available")
                    try:
                        logger.info(
                            "🔐 TOKEN STORE: get_token fetched",
                            extra={
                                "meta": {
                                    "user_id": user_id,
                                    "provider": provider,
                                    "db_path": self.db_path,
                                    "expires_at": t.expires_at,
                                    "is_valid": t.is_valid,
                                }
                            },
                        )
                    except Exception:
                        pass
                    return t

                return None

        except Exception as e:
            logger.error(f"Failed to get token for {user_id}@{provider}: {e}")
            return None

    async def get_all_user_tokens(self, user_id: str) -> list[ThirdPartyToken]:
        """
        Get all valid tokens for a user across all providers.

        Args:
            user_id: User identifier

        Returns:
            List of valid tokens for the user
        """
        try:
            await self._ensure_table()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    """
                    SELECT
                        id,
                        user_id,
                        provider,
                        access_token,
                        access_token_enc,
                        refresh_token,
                        refresh_token_enc,
                        envelope_key_version,
                        last_refresh_at,
                        refresh_error_count,
                        scope,
                        expires_at,
                        created_at,
                        updated_at,
                        is_valid
                    FROM third_party_tokens
                    WHERE user_id = ? AND is_valid = 1
                    ORDER BY provider, created_at DESC
                    """,
                    (user_id,),
                )

                rows = cursor.fetchall()
                return [ThirdPartyToken.from_db_row(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get tokens for user {user_id}: {e}")
            return []

    async def mark_invalid(self, user_id: str, provider: str) -> bool:
        """
        Mark all valid tokens for the given user and provider as invalid.

        Args:
            user_id: User identifier
            provider: Provider name

        Returns:
            True if successful, False otherwise
        """
        try:
            await self._ensure_table()

            async with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    now = int(__import__("time").time())
                    cursor.execute("""
                        UPDATE third_party_tokens
                        SET is_valid = 0, updated_at = ?
                        WHERE user_id = ? AND provider = ? AND is_valid = 1
                    """, (now, user_id, provider))

                    conn.commit()
                    return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Failed to mark token invalid for {user_id}@{provider}: {e}")
            return False

    async def update_token(self, token_id: str, updates: TokenUpdate) -> bool:
        """
        Update specific fields of a token.

        Args:
            token_id: Token ID to update
            updates: Fields to update

        Returns:
            True if successful, False otherwise
        """
        if not updates.has_updates():
            return True

        try:
            await self._ensure_table()

            async with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    # Build dynamic update query
                    update_fields = []
                    values = []

                    if updates.access_token is not None:
                        update_fields.append("access_token = ?")
                        values.append(updates.access_token)

                    if updates.refresh_token is not None:
                        update_fields.append("refresh_token = ?")
                        values.append(updates.refresh_token)

                    if updates.scope is not None:
                        update_fields.append("scope = ?")
                        values.append(updates.scope)

                    if updates.expires_at is not None:
                        update_fields.append("expires_at = ?")
                        values.append(updates.expires_at)

                    if updates.is_valid is not None:
                        update_fields.append("is_valid = ?")
                        values.append(1 if updates.is_valid else 0)

                    if not update_fields:
                        return True

                    # Add updated_at and WHERE clause
                    update_fields.append("updated_at = ?")
                    values.append(int(__import__("time").time()))
                    values.append(token_id)

                    query = f"""
                        UPDATE third_party_tokens
                        SET {', '.join(update_fields)}
                        WHERE id = ?
                    """

                    cursor.execute(query, values)
                    conn.commit()

                    return cursor.rowcount > 0

        except Exception as e:
            logger.error(f"Failed to update token {token_id}: {e}")
            return False

    async def cleanup_expired_tokens(self, max_age_seconds: int = 86400 * 30) -> int:
        """
        Clean up old invalid tokens.

        Args:
            max_age_seconds: Maximum age of invalid tokens to keep (default: 30 days)

        Returns:
            Number of tokens cleaned up
        """
        try:
            await self._ensure_table()

            async with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()

                    cutoff_time = int(__import__("time").time()) - max_age_seconds

                    cursor.execute("""
                        DELETE FROM third_party_tokens
                        WHERE is_valid = 0 AND updated_at < ?
                    """, (cutoff_time,))

                    conn.commit()
                    return cursor.rowcount

        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {e}")
            return 0

    async def get_token_stats(self) -> dict:
        """
        Get statistics about stored tokens.

        Returns:
            Dictionary with token statistics
        """
        try:
            await self._ensure_table()

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Total tokens
                cursor.execute("SELECT COUNT(*) FROM third_party_tokens")
                total_tokens = cursor.fetchone()[0]

                # Valid tokens
                cursor.execute("SELECT COUNT(*) FROM third_party_tokens WHERE is_valid = 1")
                valid_tokens = cursor.fetchone()[0]

                # Tokens by provider
                cursor.execute("""
                    SELECT provider, COUNT(*) as count
                    FROM third_party_tokens
                    WHERE is_valid = 1
                    GROUP BY provider
                    ORDER BY count DESC
                """)
                provider_stats = {row[0]: row[1] for row in cursor.fetchall()}

                return {
                    "total_tokens": total_tokens,
                    "valid_tokens": valid_tokens,
                    "invalid_tokens": total_tokens - valid_tokens,
                    "providers": provider_stats
                }

        except Exception as e:
            logger.error(f"Failed to get token stats: {e}")
            return {}


# Global instance for use across the application
token_dao = TokenDAO()


# Convenience functions
async def upsert_token(token: ThirdPartyToken) -> bool:
    """Convenience function to upsert a token."""
    return await token_dao.upsert_token(token)


async def get_token(user_id: str, provider: str) -> Optional[ThirdPartyToken]:
    """Convenience function to get a token."""
    return await token_dao.get_token(user_id, provider)


async def get_all_user_tokens(user_id: str) -> list[ThirdPartyToken]:
    """Convenience function to get all user tokens."""
    return await token_dao.get_all_user_tokens(user_id)


async def mark_invalid(user_id: str, provider: str) -> bool:
    """Convenience function to mark tokens as invalid."""
    return await token_dao.mark_invalid(user_id, provider)
