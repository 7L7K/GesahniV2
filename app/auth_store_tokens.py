from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from typing import Optional

from .models.third_party_tokens import ThirdPartyToken, TokenQuery, TokenUpdate
from .crypto_tokens import encrypt_token, decrypt_token
from .service_state import set_status as set_service_status_json

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
                        provider_sub           TEXT,
                        access_token           TEXT NOT NULL,
                        access_token_enc       BLOB,
                        refresh_token          TEXT,
                        refresh_token_enc      BLOB,
                        envelope_key_version   INTEGER DEFAULT 1,
                        last_refresh_at        INTEGER DEFAULT 0,
                        refresh_error_count    INTEGER DEFAULT 0,
                        scope                  TEXT,
                        service_state          TEXT,
                        expires_at             INTEGER NOT NULL,
                        created_at             INTEGER NOT NULL,
                        updated_at             INTEGER NOT NULL,
                        is_valid               INTEGER DEFAULT 1
                    )
                    """
                )

                # Ensure WAL + a reasonable busy timeout to avoid transient locks
                try:
                    cursor.execute("PRAGMA journal_mode=WAL")
                    cursor.execute("PRAGMA busy_timeout=2500")
                except Exception:
                    pass

                # Backfill missing columns for older databases
                try:
                    cursor.execute("PRAGMA table_info(third_party_tokens)")
                    cols = {row[1] for row in cursor.fetchall()}
                except Exception:
                    cols = set()

                # Define required columns and their SQL definitions for ALTER
                required_cols = {
                    "provider_sub": "TEXT",
                    "provider_iss": "TEXT",
                    "access_token_enc": "BLOB",
                    "refresh_token_enc": "BLOB",
                    "envelope_key_version": "INTEGER DEFAULT 1",
                    "last_refresh_at": "INTEGER DEFAULT 0",
                    "refresh_error_count": "INTEGER DEFAULT 0",
                    "service_state": "TEXT",
                    "scope_union_since": "INTEGER DEFAULT 0",
                    "scope_last_added_from": "TEXT",
                    "replaced_by_id": "TEXT",
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

                # Unique constraint for valid tokens: (user_id, provider, provider_sub)
                cursor.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_tokens_user_provider_iss_sub_unique
                    ON third_party_tokens (user_id, provider, provider_iss, provider_sub)
                    WHERE is_valid = 1
                """)

                conn.commit()

    async def _apply_repo_migration(self) -> None:
        """Attempt to apply the packaged migration SQL (002_add_access_token_enc.sql).

        This is best-effort and only used to remediate local dev DB schema drift.
        """
        try:
            here = os.path.dirname(__file__)
            migration_path = os.path.join(here, "migrations", "002_add_access_token_enc.sql")
            if os.path.exists(migration_path):
                with open(migration_path, "r", encoding="utf-8") as f:
                    sql = f.read()
                # Execute the migration SQL in a single script run
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    cur.executescript(sql)
                    conn.commit()
                    logger.info("Applied repository migration: 002_add_access_token_enc.sql", extra={"meta": {"migration": migration_path}})
        except Exception as e:
            logger.warning(f"Repository migration application failed: {e}")

    async def ensure_schema_migrated(self) -> None:
        """Ensure schema is up to date with a simple backup + migrate step."""
        try:
            # Backup once per process start if file exists
            if os.path.exists(self.db_path):
                bkp = f"{self.db_path}.bak"
                try:
                    import shutil

                    if not os.path.exists(bkp):
                        shutil.copy2(self.db_path, bkp)
                except Exception:
                    pass
            await self._ensure_table()
            # Backfill legacy rows: ensure scope_union_since and provider_iss presence
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    # Populate scope_union_since from created_at when missing/zero
                    cur.execute("SELECT id, created_at, scope_union_since FROM third_party_tokens WHERE IFNULL(scope_union_since,0) = 0")
                    rows = cur.fetchall()
                    migrated = 0
                    for r in rows:
                        tid, created_at, _ = r[0], int(r[1] or 0), int(r[2] or 0)
                        if created_at:
                            cur.execute("UPDATE third_party_tokens SET scope_union_since = ? WHERE id = ?", (created_at, tid))
                            migrated += 1

                    # For Google rows lacking provider_iss, we cannot reliably reconstruct
                    # issuer metadata in all environments; mark them invalid and annotate
                    # service_state to prompt users to reconnect.
                    cur.execute("SELECT id FROM third_party_tokens WHERE provider = 'google' AND (provider_iss IS NULL OR provider_iss = '') AND is_valid = 1")
                    bad = cur.fetchall()
                    invalidated = 0
                    ts = int(__import__("time").time())
                    for (bad_id,) in bad:
                        # Set is_valid=0 and write maintenance_required into service_state
                        try:
                            cur.execute("SELECT service_state FROM third_party_tokens WHERE id = ?", (bad_id,))
                            row = cur.fetchone()
                            prev = row[0] if row else None
                            from .service_state import set_service_error

                            new_state = set_service_error(prev, "gmail", "maintenance_required")
                            cur.execute("UPDATE third_party_tokens SET is_valid = 0, updated_at = ?, service_state = ? WHERE id = ?", (ts, new_state, bad_id))
                            invalidated += 1
                        except Exception:
                            continue

                    if migrated or invalidated:
                        logger.info("Token store backfill completed", extra={"meta": {"scope_union_since_migrated": migrated, "google_invalidated": invalidated}})
                    conn.commit()
            except Exception as e:
                logger.warning("Token store backfill failed", extra={"meta": {"error": str(e)}})
        except Exception as e:
            logger.error("Token store schema migration failed", extra={"meta": {"error": str(e)}})

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

            max_attempts = 4
            attempts = 0
            backoffs = [0.05, 0.1, 0.2, 0.4]
            while attempts < max_attempts:
                try:
                    async with self._lock:
                        # Open connection with a short timeout and use WAL + busy_timeout
                        with sqlite3.connect(self.db_path, isolation_level=None, timeout=2.5) as conn:
                            cursor = conn.cursor()
                            try:
                                cursor.execute("PRAGMA journal_mode=WAL")
                                cursor.execute("PRAGMA busy_timeout=2500")
                            except Exception:
                                pass
                            # Acquire IMMEDIATE transaction to emulate SELECT ... FOR UPDATE
                            cursor.execute("BEGIN IMMEDIATE")

                            # Ensure provider_iss presence on Google tokens (do not allow NULL issuer)
                            if not token.provider_iss:
                                raise ValueError("provider_iss is required for stored tokens")
                            # For Google provider, require provider_sub as well
                            if token.provider == "google" and not token.provider_sub:
                                raise ValueError("provider_sub is required for google tokens")

                            # Normalize incoming scope
                            def _normalize_scope(s: str | None) -> str | None:
                                if not s:
                                    return None
                                items = [x.strip().lower() for x in s.split() if x and x.strip()]
                                items = sorted(set(items))
                                return " ".join(items) if items else None

                            token.scope = _normalize_scope(token.scope)

                            # Select previous valid row for this (user,provider,provider_sub)
                            prev_id = None
                            cursor.execute(
                                """
                                SELECT id, scope, scope_union_since FROM third_party_tokens
                                WHERE user_id = ? AND provider = ? AND IFNULL(provider_iss,'') = IFNULL(?, '') AND IFNULL(provider_sub,'') = IFNULL(?, '') AND is_valid = 1
                                ORDER BY created_at DESC LIMIT 1
                                """,
                                (token.user_id, token.provider, token.provider_iss, token.provider_sub),
                            )
                            row_prev = cursor.fetchone()
                            if row_prev:
                                prev_id = row_prev[0]
                                prev_scope_raw = row_prev[1] or ""
                                prev_scopes = set([x.strip().lower() for x in prev_scope_raw.split() if x and x.strip()])
                                curr_scopes = set([x.strip().lower() for x in (token.scope or "").split() if x and x.strip()])
                                merged = prev_scopes | curr_scopes
                                token.scope = " ".join(sorted(merged)) if merged else None
                                token.scope_union_since = int(row_prev[2] or token.created_at)
                                # Record last added from when new scopes arrive
                                new_added = merged - prev_scopes
                                if new_added:
                                    token.scope_last_added_from = token.id
                            else:
                                token.scope_union_since = token.created_at

                            # Encrypt tokens if present
                            refresh_token_enc = None
                            envelope_key_version = 1
                            last_refresh_at = 0
                            refresh_error_count = 0
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

                            insert_tuple = (
                                token.id,
                                token.user_id,
                                token.provider,
                                token.provider_sub,
                                token.provider_iss,
                                token.access_token,
                                access_token_enc,
                                None if refresh_token_enc else token.refresh_token,
                                refresh_token_enc,
                                envelope_key_version,
                                last_refresh_at,
                                refresh_error_count,
                                token.scope,
                                token.service_state,
                                token.scope_union_since,
                                token.scope_last_added_from,
                                token.replaced_by_id,
                                token.expires_at,
                                token.created_at,
                                token.updated_at,
                                1 if token.is_valid else 0,
                            )

                            try:
                                cursor.execute(
                                    """
                                    INSERT INTO third_party_tokens
                                    (id, user_id, provider, provider_sub, provider_iss, access_token, access_token_enc, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count,
                                     scope, service_state, scope_union_since, scope_last_added_from, replaced_by_id, expires_at, created_at, updated_at, is_valid)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    """,
                                    insert_tuple,
                                )
                            except sqlite3.OperationalError as op_e:
                                msg = str(op_e).lower()
                                if "no column" in msg or "has no column" in msg or "no such column" in msg:
                                    logger.warning("Detected schema mismatch, attempting to apply migration", extra={"meta": {"error": str(op_e)}})
                                    try:
                                        await self._apply_repo_migration()
                                        cursor.execute(
                                            """
                                            INSERT INTO third_party_tokens
                                            (id, user_id, provider, provider_sub, provider_iss, access_token, access_token_enc, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count,
                                             scope, service_state, scope_union_since, scope_last_added_from, replaced_by_id, expires_at, created_at, updated_at, is_valid)
                                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                            """,
                                            insert_tuple,
                                        )
                                    except Exception:
                                        raise
                                else:
                                    raise

                            # Invalidate prior row and link lineage in same transaction
                            try:
                                if prev_id:
                                    cursor.execute(
                                        """
                                        UPDATE third_party_tokens
                                        SET is_valid = 0, updated_at = ?, replaced_by_id = ?
                                        WHERE id = ?
                                        """,
                                        (token.updated_at, token.id, prev_id),
                                    )
                            except Exception:
                                pass

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
                except sqlite3.OperationalError as oe:
                    if "database is locked" in str(oe).lower() and attempts < max_attempts - 1:
                        import random

                        sleep_for = backoffs[attempts] * (1 + (random.random() - 0.5) * 0.3)
                        attempts += 1
                        await asyncio.sleep(sleep_for)
                        continue
                    raise

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

    async def get_token(self, user_id: str, provider: str, provider_sub: Optional[str] = None) -> Optional[ThirdPartyToken]:
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
                if provider_sub is None:
                    cursor.execute(
                        """
                        SELECT
                            id,
                            user_id,
                            provider,
                            provider_sub,
                            provider_iss,
                            access_token,
                            access_token_enc,
                            refresh_token,
                            refresh_token_enc,
                            envelope_key_version,
                            last_refresh_at,
                            refresh_error_count,
                            scope,
                            service_state,
                            scope_union_since,
                            scope_last_added_from,
                            replaced_by_id,
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
                else:
                    cursor.execute(
                        """
                        SELECT
                            id,
                            user_id,
                            provider,
                            provider_sub,
                            provider_iss,
                            access_token,
                            access_token_enc,
                            refresh_token,
                            refresh_token_enc,
                            envelope_key_version,
                            last_refresh_at,
                            refresh_error_count,
                            scope,
                            service_state,
                            scope_union_since,
                            scope_last_added_from,
                            replaced_by_id,
                            expires_at,
                            created_at,
                            updated_at,
                            is_valid
                        FROM third_party_tokens
                        WHERE user_id = ? AND provider = ? AND IFNULL(provider_sub,'') = IFNULL(?, '') AND is_valid = 1
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (user_id, provider, provider_sub),
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

    async def get_canonical_row(self, user_id: str, provider: str, provider_iss: str, provider_sub: Optional[str]) -> Optional[ThirdPartyToken]:
        """Return the single valid canonical row for (user,provider,provider_iss,provider_sub) or None.

        This helper enforces that exactly one valid row exists; returns the latest valid row if present.
        """
        try:
            await self._ensure_table()
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT id, user_id, provider, provider_sub, provider_iss, access_token, access_token_enc, refresh_token, refresh_token_enc, envelope_key_version, last_refresh_at, refresh_error_count, scope, service_state, scope_union_since, scope_last_added_from, replaced_by_id, expires_at, created_at, updated_at, is_valid
                    FROM third_party_tokens
                    WHERE user_id = ? AND provider = ? AND IFNULL(provider_iss,'') = IFNULL(?, '') AND IFNULL(provider_sub,'') = IFNULL(?, '') AND is_valid = 1
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (user_id, provider, provider_iss or "", provider_sub or ""),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return ThirdPartyToken.from_db_row(row)
        except Exception as e:
            logger.error("Failed to fetch canonical row", extra={"meta": {"error": str(e), "user_id": user_id, "provider": provider}})
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
                        provider_sub,
                        provider_iss,
                        access_token,
                        access_token_enc,
                        refresh_token,
                        refresh_token_enc,
                        envelope_key_version,
                        last_refresh_at,
                        refresh_error_count,
                        scope,
                        service_state,
                        scope_union_since,
                        scope_last_added_from,
                        replaced_by_id,
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

    async def update_service_status(
        self,
        *,
        user_id: str,
        provider: str,
        service: str,
        status: str,
        provider_sub: Optional[str] = None,
        provider_iss: Optional[str] = None,
        last_error_code: Optional[str] = None,
    ) -> bool:
        """Update per-service state on the current valid token row.

        Finds the most recent valid row for (user, provider, iss?, sub?) and updates service_state JSON.
        """
        try:
            await self._ensure_table()
            async with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cur = conn.cursor()
                    if provider_sub is None and provider_iss is None:
                        cur.execute(
                            """
                            SELECT id, service_state FROM third_party_tokens
                            WHERE user_id = ? AND provider = ? AND is_valid = 1
                            ORDER BY created_at DESC LIMIT 1
                            """,
                            (user_id, provider),
                        )
                    else:
                        cur.execute(
                            """
                            SELECT id, service_state FROM third_party_tokens
                            WHERE user_id = ? AND provider = ? AND IFNULL(provider_sub,'') = IFNULL(?, '') AND IFNULL(provider_iss,'') = IFNULL(?, '') AND is_valid = 1
                            ORDER BY created_at DESC LIMIT 1
                            """,
                            (user_id, provider, provider_sub or "", provider_iss or ""),
                        )
                    row = cur.fetchone()
                    if not row:
                        return False
                    tid, st = row[0], row[1]
                    new_state = set_service_status_json(st, service, status, last_error_code=last_error_code)
                    now = int(__import__("time").time())
                    cur.execute(
                        "UPDATE third_party_tokens SET service_state = ?, updated_at = ? WHERE id = ?",
                        (new_state, now, tid),
                    )
                    conn.commit()
                    return cur.rowcount > 0
        except Exception as e:
            logger.error("Failed to update service state", extra={"meta": {"user_id": user_id, "provider": provider, "service": service, "status": status, "error": str(e)}})
            return False


# Global instance for use across the application
token_dao = TokenDAO()


# Convenience functions
async def upsert_token(token: ThirdPartyToken) -> bool:
    """Convenience function to upsert a token."""
    return await token_dao.upsert_token(token)


async def get_token(user_id: str, provider: str, provider_sub: Optional[str] = None) -> Optional[ThirdPartyToken]:
    """Convenience function to get a token.

    If `provider_sub` is provided (e.g., Google OIDC `sub`), selects the matching row.
    """
    return await token_dao.get_token(user_id, provider, provider_sub)


async def get_all_user_tokens(user_id: str) -> list[ThirdPartyToken]:
    """Convenience function to get all user tokens."""
    return await token_dao.get_all_user_tokens(user_id)


async def mark_invalid(user_id: str, provider: str) -> bool:
    """Convenience function to mark tokens as invalid."""
    return await token_dao.mark_invalid(user_id, provider)
