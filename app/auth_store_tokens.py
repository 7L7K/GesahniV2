"""
PostgreSQL-based token storage for third-party OAuth tokens.

This module provides secure storage and retrieval of OAuth tokens using PostgreSQL
and SQLAlchemy ORM. All tokens are encrypted at rest using envelope encryption.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, desc, func, select, update
from sqlalchemy.exc import IntegrityError

from .crypto_tokens import encrypt_token
from .db.core import get_async_db
from .db.models import ThirdPartyToken as ThirdPartyTokenModel
from .metrics import TOKEN_REFRESH_OPERATIONS, TOKEN_STORE_OPERATIONS
from .models.third_party_tokens import ThirdPartyToken
from .service_state import set_status as set_service_status_json
from .settings import settings

logger = logging.getLogger(__name__)


def _epoch_seconds(value: int | float | datetime | None) -> int:
    """Normalize various timestamp representations to epoch seconds."""
    if value is None:
        return 0
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return int(value.timestamp())
    if isinstance(value, float):
        return int(value)
    return int(value)


def _default_db_path() -> str:
    """Get the default database path for backward compatibility.

    This function is kept for backward compatibility with tests that expect
    a SQLite database path. Since this module now uses PostgreSQL, this
    returns a default SQLite path for testing purposes.
    """
    import os
    from pathlib import Path

    # Check for environment override first
    env_path = os.getenv("TOKEN_DB")
    if env_path:
        return env_path

    # Default to a test database path
    return str(Path(__file__).parent.parent / "tokens.db")


class TokenDAO:
    """Data Access Object for third-party tokens using PostgreSQL."""

    def __init__(self):
        self._lock = asyncio.Lock()

    async def _ensure_table(self) -> None:
        """PostgreSQL schema is managed by migrations, no runtime table creation needed."""
        logger.info("🔐 TOKEN STORE: PostgreSQL schema assumed to be migrated")
        pass

    async def ensure_schema_migrated(self) -> None:
        """PostgreSQL schema migrations are handled externally."""
        await self._ensure_table()

    async def upsert_token(self, token: ThirdPartyToken) -> bool:
        """
        Insert or update a token using PostgreSQL/SQLAlchemy.

        Args:
            token: The token to upsert

        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()

        # Generate unique request ID for tracking this operation
        import secrets

        req_id = f"upsert_{secrets.token_hex(4)}"

        # Convert user_id to UUID for database operations
        from app.util.ids import to_uuid

        db_user_id = str(to_uuid(token.user_id))

        logger.info(
            "🔐 TOKEN STORE: Starting upsert operation",
            extra={
                "meta": {
                    "req_id": req_id,
                    "token_id": token.id,
                    "user_id": token.user_id,
                    "db_user_id": db_user_id,
                    "provider": token.provider,
                    "identity_id": getattr(token, "identity_id", None),
                    "provider_sub": getattr(token, "provider_sub", None),
                    "expires_at": token.expires_at,
                }
            },
        )

        # Validate token before attempting storage
        if settings.STRICT_CONTRACTS:
            if not self._validate_token_for_storage(token):
                logger.warning(
                    "🔐 TOKEN STORE: Invalid token rejected",
                    extra={
                        "meta": {
                            "token_id": token.id,
                            "user_id": token.user_id,
                            "provider": token.provider,
                        }
                    },
                )
                try:
                    TOKEN_STORE_OPERATIONS.labels(
                        operation="upsert",
                        provider=token.provider,
                        result="invalid_token",
                    ).inc()
                except Exception:
                    pass
                return False

        # Normalize scopes once
        def _normalize_scopes(s: str | list | None) -> str | None:
            if not s:
                return None
            if isinstance(s, list):
                items = [str(x).strip().lower() for x in s if str(x).strip()]
            elif isinstance(s, str):
                items = (
                    [x.strip().lower() for x in s.split(",") if x.strip()]
                    if "," in s
                    else [x.strip().lower() for x in s.split() if x.strip()]
                )
            else:
                items = [x.strip().lower() for x in str(s).split() if x.strip()]
            items = sorted(set(items))
            return " ".join(items) if items else None

        token.scopes = _normalize_scopes(token.scopes)

        # Encrypt tokens (write only *_enc columns)
        access_token_enc = (
            encrypt_token(token.access_token) if token.access_token else None
        )
        refresh_token_enc = (
            encrypt_token(token.refresh_token) if token.refresh_token else None
        )

        # Contract validation (Spotify) before persist (keeps tests honest)
        if (
            token.provider == "spotify"
            and settings.STRICT_CONTRACTS
            and not settings.TEST_MODE
        ):
            if not await self._validate_spotify_token_contract(token):
                TOKEN_STORE_OPERATIONS.labels(
                    operation="upsert",
                    provider=token.provider,
                    result="invalid_contract",
                ).inc()  # type: ignore
                return False

        # Prepare values
        now_dt = datetime.now(UTC)
        exp_dt = (
            datetime.fromtimestamp(token.expires_at, UTC)
            if isinstance(token.expires_at, (int, float))
            else token.expires_at
        )

        # Retry logic for IntegrityError (race conditions on unique constraints)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with self._lock:
                    async with get_async_db() as session:
                        # Atomic upsert: write *_enc only, conflict on (user_id, provider), union scope in SQL
                        from sqlalchemy import text

                        upsert_stmt = text(
                            """
                            INSERT INTO tokens.third_party_tokens
                            (user_id, provider, provider_sub, access_token_enc, refresh_token_enc,
                             scope, expires_at, updated_at, is_valid)
                            VALUES
                            (:user_id, :provider, :provider_sub, :access_token_enc, :refresh_token_enc,
                             :scope, :expires_at, :updated_at, TRUE)
                            ON CONFLICT (user_id, provider) DO UPDATE SET
                              access_token_enc  = EXCLUDED.access_token_enc,
                              refresh_token_enc = EXCLUDED.refresh_token_enc,
                              -- string union: existing scope + new scope, collapsed to single spaces
                              scope = trim(both ' ' from regexp_replace(
                                        (coalesce(tokens.third_party_tokens.scope,'') || ' ' || coalesce(EXCLUDED.scope,'')),
                                        '(\\s+)', ' ', 'g')),
                              provider_sub = coalesce(EXCLUDED.provider_sub, tokens.third_party_tokens.provider_sub),
                              expires_at   = EXCLUDED.expires_at,
                              is_valid     = TRUE,
                              updated_at   = EXCLUDED.updated_at
                        """
                        )

                        await session.execute(
                            upsert_stmt,
                            {
                                "user_id": db_user_id,
                                "provider": token.provider,
                                "provider_sub": token.provider_sub,  # may be None if unknown yet
                                "access_token_enc": access_token_enc,
                                "refresh_token_enc": refresh_token_enc,
                                "scope": token.scopes,  # normalized string
                                "expires_at": exp_dt,
                                "updated_at": now_dt,
                            },
                        )
                        await session.commit()

                        logger.info(
                            "🔐 TOKEN STORE: Token upsert successful",
                            extra={
                                "meta": {
                                    "req_id": req_id,
                                    "token_id": token.id,
                                    "user_id": token.user_id,
                                    "provider": token.provider,
                                    "expires_at": token.expires_at,
                                    "duration_ms": int(
                                        (time.time() - start_time) * 1000
                                    ),
                                    "attempt": attempt + 1,
                                }
                            },
                        )

                        try:
                            TOKEN_STORE_OPERATIONS.labels(
                                operation="upsert",
                                provider=token.provider,
                                result="success",
                            ).inc()  # type: ignore
                        except Exception:
                            pass

                return True

            except IntegrityError as e:
                if attempt < max_retries - 1:
                    logger.warning(
                        "🔐 TOKEN STORE: IntegrityError on upsert attempt, retrying with read-then-update",
                        extra={
                            "meta": {
                                "req_id": req_id,
                                "token_id": token.id,
                                "user_id": token.user_id,
                                "provider": token.provider,
                                "attempt": attempt + 1,
                                "max_retries": max_retries,
                                "error_message": str(e),
                            }
                        },
                    )

                    # Read-then-update pattern for race condition handling
                    try:
                        async with self._lock:
                            async with get_async_db() as session:
                                # Try to find existing token by unique constraints
                                existing_stmt = select(ThirdPartyTokenModel).where(
                                    and_(
                                        ThirdPartyTokenModel.user_id == db_user_id,
                                        ThirdPartyTokenModel.provider == token.provider,
                                    )
                                )
                                result = await session.execute(existing_stmt)
                                existing_token = result.scalar_one_or_none()

                                if existing_token:
                                    # Update existing token
                                    existing_token.access_token_enc = access_token_enc
                                    existing_token.refresh_token_enc = refresh_token_enc

                                    # Union scopes
                                    existing_scopes = (
                                        existing_token.scopes.decode()
                                        if isinstance(existing_token.scopes, bytes)
                                        else existing_token.scopes
                                    )
                                    if existing_scopes and token.scopes:
                                        combined_scopes = set(
                                            (
                                                existing_scopes + " " + token.scopes
                                            ).split()
                                        )
                                        existing_token.scopes = " ".join(
                                            sorted(combined_scopes)
                                        )
                                    elif token.scopes:
                                        existing_token.scopes = token.scopes

                                    # Prioritize new provider_sub if present
                                    if token.provider_sub is not None:
                                        existing_token.provider_sub = token.provider_sub

                                    existing_token.expires_at = exp_dt
                                    existing_token.is_valid = True
                                    existing_token.updated_at = now_dt

                                    await session.commit()

                                    logger.info(
                                        "🔐 TOKEN STORE: Token upsert retry successful (read-then-update)",
                                        extra={
                                            "meta": {
                                                "req_id": req_id,
                                                "token_id": token.id,
                                                "user_id": token.user_id,
                                                "provider": token.provider,
                                                "attempt": attempt + 1,
                                            }
                                        },
                                    )
                                    return True
                                else:
                                    # No existing token found, this shouldn't happen given the IntegrityError
                                    # but continue to next retry attempt
                                    continue

                    except Exception as retry_e:
                        logger.warning(
                            "🔐 TOKEN STORE: Read-then-update failed, continuing to retry",
                            extra={
                                "meta": {
                                    "req_id": req_id,
                                    "token_id": token.id,
                                    "user_id": token.user_id,
                                    "provider": token.provider,
                                    "attempt": attempt + 1,
                                    "retry_error": str(retry_e),
                                }
                            },
                        )
                        continue
                else:
                    # Final attempt failed
                    logger.error(
                        "🔐 TOKEN STORE: Token upsert failed after all retries",
                        extra={
                            "meta": {
                                "req_id": req_id,
                                "token_id": token.id,
                                "user_id": token.user_id,
                                "provider": token.provider,
                                "error_type": "IntegrityError",
                                "error_message": str(e),
                                "max_retries": max_retries,
                                "operation": "upsert_failed",
                            }
                        },
                    )
                    return False

            except Exception as e:
                logger.error(
                    "🔐 TOKEN STORE: Token upsert failed",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "user_id": token.user_id,
                            "provider": token.provider,
                            "error_type": type(e).__name__,
                            "error_message": str(e),
                            "operation": "upsert_failed",
                        }
                    },
                )
                return False

    async def get_token(
        self, user_id: str, provider: str, provider_sub: str | None = None
    ) -> ThirdPartyToken | None:
        """
        Retrieve a valid token for the given user and provider.

        Args:
            user_id: User identifier
            provider: Provider name
            provider_sub: Provider sub-identifier (optional)

        Returns:
            Token if found and valid, None otherwise
        """
        # Convert user_id to UUID for database operations
        from app.util.ids import to_uuid

        db_user_id = str(to_uuid(user_id))

        async with get_async_db() as session:
            try:
                if provider_sub is None:
                    stmt = (
                        select(ThirdPartyTokenModel)
                        .where(
                            and_(
                                ThirdPartyTokenModel.user_id == db_user_id,
                                ThirdPartyTokenModel.provider == provider,
                                ThirdPartyTokenModel.is_valid.is_(True),
                            )
                        )
                        .order_by(desc(ThirdPartyTokenModel.created_at))
                        .limit(1)
                    )
                else:
                    stmt = (
                        select(ThirdPartyTokenModel)
                        .where(
                            and_(
                                ThirdPartyTokenModel.user_id == db_user_id,
                                ThirdPartyTokenModel.provider == provider,
                                ThirdPartyTokenModel.provider_sub == provider_sub,
                                ThirdPartyTokenModel.is_valid.is_(True),
                            )
                        )
                        .order_by(desc(ThirdPartyTokenModel.created_at))
                        .limit(1)
                    )

                result = await session.execute(stmt)
                token_model = result.scalar_one_or_none()

                if not token_model:
                    return None

                # Decrypt tokens if needed
                access_token = token_model.access_token
                refresh_token = token_model.refresh_token

                if token_model.access_token_enc:
                    try:
                        from .crypto_tokens import decrypt_token

                        access_token = decrypt_token(token_model.access_token_enc)
                    except Exception:
                        logger.warning("Failed to decrypt access_token_enc")

                if token_model.refresh_token_enc:
                    try:
                        from .crypto_tokens import decrypt_token

                        refresh_token = decrypt_token(token_model.refresh_token_enc)
                    except Exception:
                        logger.warning("Failed to decrypt refresh_token_enc")

                # Create ThirdPartyToken object
                token = ThirdPartyToken(
                    id=token_model.id,
                    user_id=token_model.user_id,
                    identity_id=token_model.identity_id,
                    provider=token_model.provider,
                    provider_sub=(
                        token_model.provider_sub.decode()
                        if isinstance(token_model.provider_sub, bytes)
                        else token_model.provider_sub
                    ),
                    provider_iss=(
                        token_model.provider_iss.decode()
                        if isinstance(token_model.provider_iss, bytes)
                        else token_model.provider_iss
                    ),
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=_epoch_seconds(token_model.expires_at),
                    scopes=(
                        token_model.scopes.decode()
                        if isinstance(token_model.scopes, bytes)
                        else token_model.scopes
                    ),
                    service_state=token_model.service_state,
                    scope_union_since=_epoch_seconds(token_model.scope_union_since),
                    scope_last_added_from=token_model.scope_last_added_from,
                    replaced_by_id=token_model.replaced_by_id,
                    created_at=_epoch_seconds(token_model.created_at),
                    updated_at=_epoch_seconds(token_model.updated_at),
                    is_valid=token_model.is_valid,
                )

                logger.info(
                    "🔐 TOKEN STORE: get_token fetched",
                    extra={
                        "meta": {
                            "user_id": user_id,
                            "provider": provider,
                            "expires_at": token.expires_at,
                            "is_valid": token.is_valid,
                        }
                    },
                )

                result_token = token
                return result_token
            except Exception as e:
                error_msg = str(e)
                error_type = type(e).__name__

                # Check if this is a database connectivity issue
                if "connection" in error_msg.lower() or "psycopg" in error_type.lower():
                    logger.error(
                        "🚨 DATABASE CONNECTION FAILURE in get_token",
                        extra={
                            "meta": {
                                "user_id": user_id,
                                "provider": provider,
                                "error_type": error_type,
                                "error_message": error_msg,
                                "severity": "CRITICAL",
                                "cause": "PostgreSQL database not accessible",
                                "solution": "Start PostgreSQL: pg_ctl -D /usr/local/var/postgresql@14 start",
                            }
                        },
                    )
                    logger.error(
                        "💡 SOLUTION: Check if PostgreSQL is running and DATABASE_URL is correct"
                    )
                else:
                    logger.error(
                        "🔐 TOKEN STORE: get_token failed",
                        extra={
                            "meta": {
                                "user_id": user_id,
                                "provider": provider,
                                "error_type": error_type,
                                "error_message": error_msg,
                            }
                        },
                    )
                return None

    async def get_all_user_tokens(self, user_id: str) -> list[ThirdPartyToken]:
        """
        Get all valid tokens for a user across all providers.

        Args:
            user_id: User identifier

        Returns:
            List of valid tokens for the user
        """
        # Convert user_id to UUID for database operations
        from app.util.ids import to_uuid

        db_user_id = str(to_uuid(user_id))

        try:
            async with get_async_db() as session:
                stmt = (
                    select(ThirdPartyTokenModel)
                    .where(
                        and_(
                            ThirdPartyTokenModel.user_id == db_user_id,
                            ThirdPartyTokenModel.is_valid.is_(True),
                        )
                    )
                    .order_by(
                        ThirdPartyTokenModel.provider,
                        desc(ThirdPartyTokenModel.created_at),
                    )
                )

                result = await session.execute(stmt)
                token_models = result.scalars().all()

                tokens = []
                for token_model in token_models:
                    # Decrypt tokens if needed
                    access_token = token_model.access_token
                    refresh_token = token_model.refresh_token

                    if token_model.access_token_enc:
                        try:
                            from .crypto_tokens import decrypt_token

                            access_token = decrypt_token(token_model.access_token_enc)
                        except Exception:
                            logger.warning("Failed to decrypt access_token_enc")

                    if token_model.refresh_token_enc:
                        try:
                            from .crypto_tokens import decrypt_token

                            refresh_token = decrypt_token(token_model.refresh_token_enc)
                        except Exception:
                            logger.warning("Failed to decrypt refresh_token_enc")

                    token = ThirdPartyToken(
                        id=token_model.id,
                        user_id=token_model.user_id,
                        identity_id=token_model.identity_id,
                        provider=token_model.provider,
                        provider_sub=(
                            token_model.provider_sub.decode()
                            if isinstance(token_model.provider_sub, bytes)
                            else token_model.provider_sub
                        ),
                        provider_iss=(
                            token_model.provider_iss.decode()
                            if isinstance(token_model.provider_iss, bytes)
                            else token_model.provider_iss
                        ),
                        access_token=access_token,
                        refresh_token=refresh_token,
                        expires_at=_epoch_seconds(token_model.expires_at),
                        scopes=(
                            token_model.scopes.decode()
                            if isinstance(token_model.scopes, bytes)
                            else token_model.scopes
                        ),
                        service_state=token_model.service_state,
                        scope_union_since=_epoch_seconds(token_model.scope_union_since),
                        scope_last_added_from=token_model.scope_last_added_from,
                        replaced_by_id=token_model.replaced_by_id,
                        created_at=_epoch_seconds(token_model.created_at),
                        updated_at=_epoch_seconds(token_model.updated_at),
                        is_valid=token_model.is_valid,
                    )
                    tokens.append(token)

                return tokens
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
        # Convert user_id to UUID for database operations
        from app.util.ids import to_uuid

        db_user_id = str(to_uuid(user_id))

        try:
            async with self._lock:
                async with get_async_db() as session:
                    stmt = (
                        update(ThirdPartyTokenModel)
                        .where(
                            and_(
                                ThirdPartyTokenModel.user_id == db_user_id,
                                ThirdPartyTokenModel.provider == provider,
                                ThirdPartyTokenModel.is_valid.is_(True),
                            )
                        )
                        .values(is_valid=False, updated_at=datetime.now(UTC))
                    )

                    result = await session.execute(stmt)
                    await session.commit()

                    # Handle unreliable rowcount (-1 with some drivers)
                    rowcount = getattr(result, "rowcount", None)
                    if rowcount is None or rowcount < 0:
                        # If rowcount is unreliable, assume success if no exception occurred
                        return True
                    return rowcount > 0

        except Exception as e:
            logger.error(f"Failed to mark token invalid for {user_id}@{provider}: {e}")
            return False

    async def update_service_status(
        self,
        *,
        user_id: str,
        provider: str,
        service: str,
        status: str,
        provider_sub: str | None = None,
        provider_iss: str | None = None,
        last_error_code: str | None = None,
    ) -> bool:
        """Update per-service state on the current valid token row."""
        try:
            async with self._lock:
                async with get_async_db() as session:
                    # Find the most recent valid token with appropriate constraints
                    base_conditions = [
                        ThirdPartyTokenModel.user_id == user_id,
                        ThirdPartyTokenModel.provider == provider,
                        ThirdPartyTokenModel.is_valid.is_(True),
                    ]

                    # Add provider-specific constraints
                    if provider_sub is not None:
                        base_conditions.append(
                            ThirdPartyTokenModel.provider_sub == provider_sub
                        )
                    if provider_iss is not None:
                        base_conditions.append(
                            ThirdPartyTokenModel.provider_iss == provider_iss
                        )

                    stmt = (
                        select(ThirdPartyTokenModel)
                        .where(and_(*base_conditions))
                        .order_by(desc(ThirdPartyTokenModel.created_at))
                        .limit(1)
                    )

                    result = await session.execute(stmt)
                    token_model = result.scalar_one_or_none()

                    if not token_model:
                        return False

                    # Update service state
                    new_state = set_service_status_json(
                        token_model.service_state,
                        service,
                        status,
                        last_error_code=last_error_code,
                    )
                    token_model.service_state = new_state
                    token_model.updated_at = datetime.now(UTC)

                    await session.commit()
                    return True

        except Exception as e:
            logger.error(
                "Failed to update service state",
                extra={
                    "meta": {
                        "user_id": user_id,
                        "provider": provider,
                        "service": service,
                        "status": status,
                        "error": str(e),
                    }
                },
            )
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
            async with self._lock:
                async with get_async_db() as session:
                    cutoff_time = datetime.now(UTC) - timedelta(seconds=max_age_seconds)

                    stmt = delete(ThirdPartyTokenModel).where(
                        and_(
                            ThirdPartyTokenModel.is_valid.is_(False),
                            ThirdPartyTokenModel.updated_at < cutoff_time,
                        )
                    )

                    result = await session.execute(stmt)
                    await session.commit()

                    # Handle unreliable rowcount (-1 with some drivers)
                    rowcount = getattr(result, "rowcount", None)
                    if rowcount is None or rowcount < 0:
                        # If rowcount is unreliable, return 0 (conservative approach)
                        return 0
                    return rowcount

        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {e}")
            return 0

    def _validate_token_for_storage(self, token: ThirdPartyToken) -> bool:
        """Validate token before storage."""
        try:
            if not token.id or not token.user_id or not token.provider:
                return False

            # Must have at least access token or refresh token
            has_access = bool(token.access_token or token.access_token_enc)
            has_refresh = bool(token.refresh_token or token.refresh_token_enc)

            if not has_access and not has_refresh:
                return False

            # Provider-specific validation
            is_test_mode = settings.TEST_MODE or (not settings.STRICT_CONTRACTS)
            if token.provider == "spotify":
                if not is_test_mode:
                    if (
                        not token.provider_iss
                        or token.provider_iss != "https://accounts.spotify.com"
                    ):
                        return False
            elif token.provider == "google":
                if not is_test_mode:
                    if (
                        not token.provider_iss
                        or token.provider_iss != "https://accounts.google.com"
                    ):
                        return False

            return True
        except Exception:
            return False

    def _validate_decrypted_tokens(self, token: ThirdPartyToken) -> bool:
        """Validate decrypted tokens are properly formatted."""
        try:
            # Basic validation: tokens should exist and have reasonable length
            if token.access_token and len(token.access_token) < 10:
                return False

            if token.refresh_token and len(token.refresh_token) < 10:
                return False

            # For strict mode, perform provider-specific validation
            if settings.STRICT_CONTRACTS and not settings.TEST_MODE:
                return self._validate_token_by_provider(token)

            return True
        except Exception:
            return False

    def _validate_token_by_provider(self, token: ThirdPartyToken) -> bool:
        """Validate token format based on provider-specific rules."""
        try:
            # Basic sanity checks for all providers
            if not token.provider:
                return False

            # Provider-specific validation
            if token.provider == "spotify":
                return self._validate_spotify_token_format(token)
            elif token.provider == "google":
                return self._validate_google_token_format(token)
            else:
                # For unknown providers, use generic validation
                return self._validate_generic_token_format(token)

        except Exception:
            return False

    def _validate_spotify_token_format(self, token: ThirdPartyToken) -> bool:
        """Validate Spotify token format - more flexible than hardcoded patterns."""
        try:
            # Check access token basic properties
            if token.access_token:
                # Allow various OAuth token formats - just check it's not obviously wrong
                if len(token.access_token) < 20:  # Reasonable minimum for OAuth tokens
                    return False
                # Check for common token characteristics (base64-like, JWT-like, etc.)
                if not any(
                    char in token.access_token
                    for char in [".", "-", "_", "+", "/", "="]
                ):
                    # If it doesn't contain common token characters, it might be malformed
                    return False

            # Check refresh token basic properties
            if token.refresh_token:
                if len(token.refresh_token) < 20:
                    return False

            return True
        except Exception:
            return False

    def _validate_google_token_format(self, token: ThirdPartyToken) -> bool:
        """Validate Google token format."""
        try:
            # Similar flexible validation for Google tokens
            if token.access_token and len(token.access_token) < 20:
                return False

            if token.refresh_token and len(token.refresh_token) < 20:
                return False

            return True
        except Exception:
            return False

    def _validate_generic_token_format(self, token: ThirdPartyToken) -> bool:
        """Validate tokens for unknown providers with basic checks."""
        try:
            # Basic validation for any OAuth provider
            if token.access_token and len(token.access_token) < 10:
                return False

            if token.refresh_token and len(token.refresh_token) < 10:
                return False

            return True
        except Exception:
            return False

    async def _validate_spotify_token_contract(self, token: ThirdPartyToken) -> bool:
        """
        Test-mode contract validation for Spotify tokens.
        Performs comprehensive validation and logs all failures.
        """
        import time

        validation_passed = True
        now = int(time.time())

        # Generate request ID for tracking this validation
        import secrets

        req_id = f"contract_{secrets.token_hex(4)}"

        logger.info(
            "🔒 CONTRACT VALIDATION: Starting Spotify token contract checks",
            extra={
                "meta": {
                    "req_id": req_id,
                    "token_id": token.id,
                    "user_id": token.user_id,
                    "provider": token.provider,
                    "identity_id": getattr(token, "identity_id", None),
                }
            },
        )

        # 1. provider == 'spotify'
        if token.provider != "spotify":
            logger.error(
                "🔒 CONTRACT VALIDATION: FAILED - provider must be 'spotify'",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "token_id": token.id,
                        "actual_provider": token.provider,
                        "expected_provider": "spotify",
                    }
                },
            )
            validation_passed = False

        # 2. provider_iss == 'https://accounts.spotify.com'
        if (
            not token.provider_iss
            or token.provider_iss != "https://accounts.spotify.com"
        ):
            logger.error(
                "🔒 CONTRACT VALIDATION: FAILED - provider_iss must be 'https://accounts.spotify.com'",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "token_id": token.id,
                        "actual_provider_iss": token.provider_iss,
                        "expected_provider_iss": "https://accounts.spotify.com",
                    }
                },
            )
            validation_passed = False

        # 3. identity_id is a non-empty TEXT that exists in auth_identities
        identity_id = getattr(token, "identity_id", None)
        if (
            not identity_id
            or not isinstance(identity_id, str)
            or not identity_id.strip()
        ):
            logger.error(
                "🔒 CONTRACT VALIDATION: FAILED - identity_id must be non-empty TEXT",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "token_id": token.id,
                        "identity_id": identity_id,
                        "identity_id_type": type(identity_id).__name__,
                    }
                },
            )
            validation_passed = False

        # 4. access_token flexible validation (no hardcoded format requirements)
        if not token.access_token:
            logger.error(
                "🔒 CONTRACT VALIDATION: FAILED - access_token is required",
                extra={"meta": {"req_id": req_id, "token_id": token.id}},
            )
            validation_passed = False
        else:
            # Flexible validation - check for reasonable OAuth token characteristics
            if len(token.access_token) < 20:
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - access_token too short",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "access_token_length": len(token.access_token),
                            "minimum_length": 20,
                        }
                    },
                )
                validation_passed = False
            elif not any(
                char in token.access_token for char in [".", "-", "_", "+", "/", "="]
            ):
                # OAuth tokens typically contain these characters
                logger.warning(
                    "🔒 CONTRACT VALIDATION: WARNING - access_token lacks common OAuth characters",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "access_token_prefix": (
                                token.access_token[:10] + "..."
                                if len(token.access_token) > 10
                                else token.access_token
                            ),
                        }
                    },
                )
                # Don't fail validation for this - just warn

        # 5. refresh_token flexible validation (no hardcoded format requirements)
        if token.refresh_token is not None:
            if len(token.refresh_token) < 20:
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - refresh_token too short",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "refresh_token_length": len(token.refresh_token),
                            "minimum_length": 20,
                        }
                    },
                )
                validation_passed = False
            elif not any(
                char in token.refresh_token for char in [".", "-", "_", "+", "/", "="]
            ):
                # OAuth tokens typically contain these characters
                logger.warning(
                    "🔒 CONTRACT VALIDATION: WARNING - refresh_token lacks common OAuth characters",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "refresh_token_prefix": (
                                token.refresh_token[:10] + "..."
                                if len(token.refresh_token) > 10
                                else token.refresh_token
                            ),
                        }
                    },
                )
                # Don't fail validation for this - just warn

        # 6. expires_at is int and expires_at - now >= 300
        if not isinstance(token.expires_at, int):
            logger.error(
                "🔒 CONTRACT VALIDATION: FAILED - expires_at must be int",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "token_id": token.id,
                        "expires_at": token.expires_at,
                        "expires_at_type": type(token.expires_at).__name__,
                    }
                },
            )
            validation_passed = False
        else:
            time_until_expiry = token.expires_at - now
            if time_until_expiry < 300:
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - expires_at too soon",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "expires_at": token.expires_at,
                            "now": now,
                            "time_until_expiry": time_until_expiry,
                            "minimum_seconds": 300,
                        }
                    },
                )
                validation_passed = False

        # 7. scopes non-empty (store as space-separated string like user-read-email user-read-private)
        scopes = getattr(token, "scopes", None)
        if not scopes:
            logger.error(
                "🔒 CONTRACT VALIDATION: FAILED - scopes is required",
                extra={
                    "meta": {"req_id": req_id, "token_id": token.id, "scopes": scopes}
                },
            )
            validation_passed = False
        else:
            # Normalize scopes to space-separated string format (consistent with upsert logic)
            def _normalize_scopes_for_contract(s: str | list | None) -> str | None:
                if not s:
                    return None
                if isinstance(s, list):
                    # Convert list to normalized scopes
                    items = [str(x).strip().lower() for x in s if x and str(x).strip()]
                elif isinstance(s, str):
                    # Handle comma-separated or space-separated strings
                    # First try splitting by commas, then by spaces if no commas found
                    if "," in s:
                        items = [
                            x.strip().lower() for x in s.split(",") if x and x.strip()
                        ]
                    else:
                        items = [
                            x.strip().lower() for x in s.split() if x and x.strip()
                        ]
                else:
                    # Convert other types to string then split
                    items = [
                        x.strip().lower() for x in str(s).split() if x and x.strip()
                    ]

                # Remove duplicates and sort
                items = sorted(set(items))
                return " ".join(items) if items else None

            normalized_scopes = _normalize_scopes_for_contract(scopes)

            if not normalized_scopes:
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - scopes cannot be empty after normalization",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "scopes": scopes,
                            "scopes_type": type(scopes).__name__,
                            "normalized_scopes": normalized_scopes,
                        }
                    },
                )
                validation_passed = False
            else:
                # Update token.scopes to normalized space-separated string format
                token.scopes = normalized_scopes

        if validation_passed:
            logger.info(
                "🔒 CONTRACT VALIDATION: SUCCESS - all checks passed",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "token_id": token.id,
                        "user_id": token.user_id,
                        "provider": token.provider,
                    }
                },
            )
        else:
            logger.error(
                "🔒 CONTRACT VALIDATION: FAILED - validation failed",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "token_id": token.id,
                        "user_id": token.user_id,
                        "provider": token.provider,
                    }
                },
            )

        return validation_passed


# Global instance for use across the application
token_dao = TokenDAO()


# Convenience functions
async def upsert_token(token: ThirdPartyToken) -> bool:
    """Convenience function to upsert a token."""
    return await token_dao.upsert_token(token)


async def get_token(
    user_id: str, provider: str, provider_sub: str | None = None
) -> ThirdPartyToken | None:
    """Convenience function to get a token."""
    return await token_dao.get_token(user_id, provider, provider_sub)


async def get_all_user_tokens(user_id: str) -> list[ThirdPartyToken]:
    """Convenience function to get all user tokens."""
    return await token_dao.get_all_user_tokens(user_id)


async def get_token_by_user_identities(
    user_id: str, provider: str
) -> ThirdPartyToken | None:
    """Convenience function to get token by user identities (alias for get_token)."""
    return await get_token(user_id, provider)


async def mark_invalid(user_id: str, provider: str) -> bool:
    """Convenience function to mark tokens as invalid."""
    return await token_dao.mark_invalid(user_id, provider)


# ============================================================================
# TOKEN REFRESH SERVICE
# ============================================================================


class TokenRefreshService:
    """Service for handling automatic token refresh with retry logic."""

    def __init__(self):
        # Per-key locks to prevent concurrent refresh for same user/provider
        self._locks: dict[str, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()  # Protects the _locks dictionary
        self._refresh_attempts = {}
        self._max_refresh_attempts = 3
        self._refresh_backoff_seconds = [1, 2, 4]  # Exponential backoff
        # In-memory backoff map to avoid aggressive refresh retries after failures
        # keyed by '{user_id}:{provider}:{provider_sub}' -> unix timestamp when next refresh allowed
        self._next_refresh_after: dict[str, float] = {}

    async def _get_lock_for_key(self, key: str) -> asyncio.Lock:
        """Get or create a lock for the given key."""
        async with self._locks_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def _cleanup_lock_if_unused(self, key: str):
        """Clean up lock if it's no longer needed (optional optimization)."""
        async with self._locks_lock:
            lock = self._locks.get(key)
            if lock and not lock.locked():
                # Only remove if not currently locked and not waiting
                # This is a simple heuristic - in practice, locks could be reused
                pass  # For now, keep locks to avoid race conditions

    async def get_valid_token_with_refresh(
        self,
        user_id: str,
        provider: str,
        provider_sub: str | None = None,
        force_refresh: bool = False,
    ) -> ThirdPartyToken | None:
        """
        Get a valid token, automatically refreshing if needed.

        Args:
            user_id: User identifier
            provider: Provider name
            provider_sub: Provider sub-identifier (optional)
            force_refresh: Force refresh even if token appears valid

        Returns:
            Valid token or None if refresh fails
        """
        # Prevent concurrent refresh for same user/provider
        lock_key = f"{user_id}:{provider}:{provider_sub or ''}"

        # Get per-key lock to allow concurrent refreshes for different identities
        refresh_lock = await self._get_lock_for_key(lock_key)

        async with refresh_lock:
            # Get current token
            token = await get_token(user_id, provider, provider_sub)

            if not token:
                logger.info(
                    "🔄 TOKEN REFRESH: No token found",
                    extra={"meta": {"user_id": user_id, "provider": provider}},
                )
                return None

            # Check if token needs refresh
            needs_refresh = force_refresh or self._should_refresh_token(token)

            if not needs_refresh:
                return token

            # Check refresh attempt limits
            attempt_key = lock_key
            attempts = self._refresh_attempts.get(attempt_key, 0)

            # Respect light backoff if recently failed
            now = time.time()
            next_allowed = self._next_refresh_after.get(attempt_key)
            if next_allowed and now < next_allowed:
                logger.info(
                    "🔄 TOKEN REFRESH: Backoff active, skipping refresh",
                    extra={
                        "meta": {
                            "user_id": user_id,
                            "provider": provider,
                            "next_allowed": next_allowed,
                        }
                    },
                )
                # Return current (possibly stale) token to avoid churn
                return token

            if attempts >= self._max_refresh_attempts:
                logger.warning(
                    "🔄 TOKEN REFRESH: Max refresh attempts exceeded",
                    extra={
                        "meta": {
                            "user_id": user_id,
                            "provider": provider,
                            "attempts": attempts,
                        }
                    },
                )
                # Mark token as invalid if we can't refresh it
                await mark_invalid(user_id, provider)
                return None

            # Attempt refresh
            refreshed_token = await self._refresh_token_for_provider(token)

            if refreshed_token:
                # Reset attempt counter on success
                self._refresh_attempts[attempt_key] = 0
                logger.info(
                    "🔄 TOKEN REFRESH: Success",
                    extra={"meta": {"user_id": user_id, "provider": provider}},
                )
                try:
                    TOKEN_REFRESH_OPERATIONS.labels(
                        provider=provider, result="success", attempt=str(attempts + 1)
                    ).inc()
                except Exception:
                    pass
                return refreshed_token
            else:
                # Increment attempt counter on failure
                self._refresh_attempts[attempt_key] = attempts + 1
                logger.warning(
                    "🔄 TOKEN REFRESH: Failed",
                    extra={
                        "meta": {
                            "user_id": user_id,
                            "provider": provider,
                            "attempts": attempts + 1,
                        }
                    },
                )
                try:
                    TOKEN_REFRESH_OPERATIONS.labels(
                        provider=provider, result="failure", attempt=str(attempts + 1)
                    ).inc()
                except Exception:
                    pass

                # If this was the last attempt, mark token invalid
                if attempts + 1 >= self._max_refresh_attempts:
                    await mark_invalid(user_id, provider)

                # On refresh failure, set light backoff to avoid polling churn (~10 minutes)
                try:
                    self._next_refresh_after[attempt_key] = time.time() + 600
                except Exception:
                    pass

                return None

    def _should_refresh_token(
        self, token: ThirdPartyToken, buffer_seconds: int = 300
    ) -> bool:
        """Determine if a token should be refreshed."""
        try:
            # Refresh if expired or will expire soon
            return token.is_expired(buffer_seconds)
        except Exception:
            # If we can't determine expiry, assume it needs refresh
            return True

    async def _refresh_token_for_provider(
        self, token: ThirdPartyToken
    ) -> ThirdPartyToken | None:
        """Refresh token based on provider."""
        try:
            if token.provider == "spotify":
                return await self._refresh_spotify_token(token)
            elif token.provider == "google":
                return await self._refresh_google_token(token)
            else:
                logger.warning(
                    "🔄 TOKEN REFRESH: Unsupported provider",
                    extra={"meta": {"provider": token.provider}},
                )
                return None
        except Exception as e:
            logger.error(
                "🔄 TOKEN REFRESH: Refresh failed",
                extra={
                    "meta": {
                        "provider": token.provider,
                        "user_id": token.user_id,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
                    }
                },
            )
            return None

    async def _refresh_spotify_token(
        self, token: ThirdPartyToken
    ) -> ThirdPartyToken | None:
        """Refresh Spotify token."""
        try:
            from .integrations.spotify.client import SpotifyClient

            client = SpotifyClient(token.user_id)

            # Use the client's refresh method
            refreshed_tokens = await client._refresh_tokens()

            # Create new token object
            refreshed_token = ThirdPartyToken(
                user_id=token.user_id,
                provider="spotify",
                access_token=refreshed_tokens.access_token,
                refresh_token=refreshed_tokens.refresh_token,
                expires_at=refreshed_tokens.expires_at,
                scopes=refreshed_tokens.scopes,
                provider_iss=token.provider_iss or "https://accounts.spotify.com",
                provider_sub=token.provider_sub,
                identity_id=token.identity_id,
            )

            # Store the refreshed token
            await upsert_token(refreshed_token)
            return refreshed_token

        except Exception as e:
            logger.error(
                "🔄 SPOTIFY REFRESH: Failed",
                extra={"meta": {"user_id": token.user_id, "error": str(e)}},
            )
            return None

    async def _refresh_google_token(
        self, token: ThirdPartyToken
    ) -> ThirdPartyToken | None:
        """Refresh Google token."""
        try:
            # Import here to avoid circular dependencies
            from .integrations.google.oauth import refresh_access_token
            from .models.third_party_tokens import ThirdPartyToken

            # Refresh the token
            token_data = await refresh_access_token(token.refresh_token)

            # Create new token object
            refreshed_token = ThirdPartyToken(
                user_id=token.user_id,
                provider="google",
                access_token=token_data.get("access_token", ""),
                refresh_token=token_data.get("refresh_token", token.refresh_token),
                expires_at=int(token_data.get("expires_at", 0)),
                scopes=token_data.get("scopes"),
                provider_iss="https://accounts.google.com",
                # provider_sub intentionally omitted; existing provider_sub will be preserved by upsert
            )

            # Store the refreshed token
            await upsert_token(refreshed_token)
            return refreshed_token

        except Exception as e:
            # Import here to avoid circular dependencies
            from .integrations.google.oauth import InvalidGrantError

            # Handle invalid_grant errors specially (user revoked consent)
            if isinstance(e, InvalidGrantError):
                logger.warning(
                    "🔄 GOOGLE REFRESH: Invalid grant detected - user revoked consent",
                    extra={
                        "meta": {
                            "user_id": token.user_id,
                            "error_type": "invalid_grant",
                        }
                    },
                )

                # Mark token as invalid to prevent further refresh attempts
                try:
                    from .models.third_party_tokens import ThirdPartyToken

                    invalid_token = ThirdPartyToken(
                        id=token.id,
                        user_id=token.user_id,
                        provider="google",
                        access_token="",  # Clear access token
                        refresh_token=None,  # Clear refresh token
                        scopes=None,
                        expires_at=0,
                        is_valid=False,  # Mark as invalid
                        provider_iss=token.provider_iss,
                        provider_sub=token.provider_sub,
                    )
                    await upsert_token(invalid_token)

                    # Emit metric for invalid_grant
                    try:
                        from .metrics import GOOGLE_REFRESH_FAILED

                        GOOGLE_REFRESH_FAILED.labels(
                            user_id=token.user_id, reason="invalid_grant"
                        ).inc()
                    except Exception:
                        pass
                except Exception as mark_err:
                    logger.error(
                        "🔄 GOOGLE REFRESH: Failed to mark token invalid",
                        extra={
                            "meta": {"user_id": token.user_id, "error": str(mark_err)}
                        },
                    )

                return None

            # For other errors, use normal backoff
            try:
                attempt_key = f"{token.user_id}:google:{token.provider_sub or ''}"
                self._next_refresh_after[attempt_key] = time.time() + 600
            except Exception:
                pass

            # Emit metric for other refresh failures
            try:
                from .metrics import GOOGLE_REFRESH_FAILED

                GOOGLE_REFRESH_FAILED.labels(
                    user_id=token.user_id, reason="other"
                ).inc()
            except Exception:
                pass

            logger.warning(
                "🔄 GOOGLE REFRESH: Failed (masked)",
                extra={
                    "meta": {"user_id": token.user_id, "error_type": type(e).__name__}
                },
            )
            return None

    def reset_refresh_attempts(
        self, user_id: str, provider: str, provider_sub: str | None = None
    ):
        """Reset refresh attempt counter for a user/provider identity."""
        attempt_key = f"{user_id}:{provider}:{provider_sub or ''}"
        self._refresh_attempts.pop(attempt_key, None)
        self._next_refresh_after.pop(attempt_key, None)

    async def cleanup_old_locks(self, max_age_seconds: int = 3600):
        """
        Clean up locks for keys that haven't been used recently.
        This prevents the locks dictionary from growing indefinitely.
        """
        # Note: This is a simple cleanup that removes locks that aren't currently locked
        # In practice, you might want more sophisticated cleanup based on last access time
        pass  # For now, let locks persist to avoid race conditions


# Global instance
token_refresh_service = TokenRefreshService()


async def get_valid_token_with_auto_refresh(
    user_id: str,
    provider: str,
    provider_sub: str | None = None,
    force_refresh: bool = False,
) -> ThirdPartyToken | None:
    """
    Convenience function to get a valid token with automatic refresh.

    This is the main entry point for getting tokens - it handles validation
    and automatic refresh when needed.
    """
    return await token_refresh_service.get_valid_token_with_refresh(
        user_id, provider, provider_sub, force_refresh
    )


# ============================================================================
# HEALTH MONITORING
# ============================================================================


async def get_token_system_health() -> dict:
    """
    Get comprehensive health status of the token system.

    Returns:
        Health status dictionary with various metrics
    """
    async with get_async_db() as session:
        try:
            # Total tokens
            stmt = select(func.count()).select_from(ThirdPartyTokenModel)
            result = await session.execute(stmt)
            total_tokens = result.scalar() or 0

            # Valid tokens
            stmt = (
                select(func.count())
                .select_from(ThirdPartyTokenModel)
                .where(ThirdPartyTokenModel.is_valid.is_(True))
            )
            result = await session.execute(stmt)
            valid_tokens = result.scalar() or 0

            # Tokens by provider
            stmt = (
                select(
                    ThirdPartyTokenModel.provider, func.count(ThirdPartyTokenModel.id)
                )
                .where(ThirdPartyTokenModel.is_valid.is_(True))
                .group_by(ThirdPartyTokenModel.provider)
            )

            result = await session.execute(stmt)
            provider_stats = {row[0]: row[1] for row in result.all()}

            # Expired tokens
            now = int(datetime.now(UTC).timestamp())
            stmt = (
                select(func.count())
                .select_from(ThirdPartyTokenModel)
                .where(
                    and_(
                        ThirdPartyTokenModel.expires_at < now,
                        ThirdPartyTokenModel.is_valid.is_(True),
                    )
                )
            )
            result = await session.execute(stmt)
            expired_tokens = result.scalar() or 0

            # Get refresh service stats
            refresh_stats = {
                "active_refresh_attempts": len(token_refresh_service._refresh_attempts),
                "max_refresh_attempts": token_refresh_service._max_refresh_attempts,
            }

            return {
                "status": "healthy",
                "timestamp": time.time(),
                "database": {
                    "total_tokens": total_tokens,
                    "valid_tokens": valid_tokens,
                    "expired_tokens": expired_tokens,
                    "providers": provider_stats,
                },
                "refresh_service": refresh_stats,
                "metrics": {
                    "token_validation_enabled": True,
                    "automatic_refresh_enabled": True,
                    "monitoring_enabled": True,
                },
            }

        except Exception as e:
            logger.error(
                "Token system health check failed",
                extra={
                    "meta": {"error_type": type(e).__name__, "error_message": str(e)}
                },
            )
            return {
                "status": "unhealthy",
                "timestamp": time.time(),
                "error": str(e),
                "database": {"status": "unknown"},
                "refresh_service": {"status": "unknown"},
            }
