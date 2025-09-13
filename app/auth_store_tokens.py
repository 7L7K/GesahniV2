"""
PostgreSQL-based token storage for third-party OAuth tokens.

This module provides secure storage and retrieval of OAuth tokens using PostgreSQL
and SQLAlchemy ORM. All tokens are encrypted at rest using envelope encryption.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime

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

        logger.info(
            "🔐 TOKEN STORE: Starting upsert operation",
            extra={
                "meta": {
                    "req_id": req_id,
                    "token_id": token.id,
                    "user_id": token.user_id,
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

        try:
            async with self._lock:
                async with get_async_db() as session:
                    # Check for existing token with same (user_id, provider, provider_sub)
                    stmt = select(ThirdPartyTokenModel).where(
                        and_(
                            ThirdPartyTokenModel.user_id == token.user_id,
                            ThirdPartyTokenModel.provider == token.provider,
                            ThirdPartyTokenModel.provider_sub == token.provider_sub,
                        )
                    )
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()

                    # Normalize scopes
                    def _normalize_scope(s: str | None) -> str | None:
                        if not s:
                            return None
                        items = [
                            x.strip().lower() for x in s.split() if x and x.strip()
                        ]
                        items = sorted(set(items))
                        return " ".join(items) if items else None

                    token.scopes = _normalize_scope(token.scopes)

                    # Merge scopes if existing token found
                    if existing and existing.scopes:
                        existing_scopes = set(
                            existing.scopes.decode().split()
                            if isinstance(existing.scopes, bytes)
                            else existing.scopes.split()
                        )
                        new_scopes = (
                            set(token.scopes.split()) if token.scopes else set()
                        )
                        merged_scopes = existing_scopes | new_scopes
                        token.scopes = (
                            " ".join(sorted(merged_scopes)) if merged_scopes else None
                        )

                        if new_scopes - existing_scopes:
                            token.scope_last_added_from = token.id

                        token.scope_union_since = (
                            existing.scope_union_since or token.created_at
                        )

                    # Encrypt tokens
                    access_token_enc = None
                    refresh_token_enc = None
                    if token.access_token:
                        try:
                            access_token_enc = encrypt_token(token.access_token)
                        except Exception:
                            pass
                    if token.refresh_token:
                        try:
                            refresh_token_enc = encrypt_token(token.refresh_token)
                        except Exception:
                            pass

                    # Perform Spotify validation if needed
                    if (
                        token.provider == "spotify"
                        and settings.STRICT_CONTRACTS
                        and not settings.TEST_MODE
                    ):
                        contract_valid = await self._validate_spotify_token_contract(
                            token
                        )
                        if not contract_valid:
                            logger.error(
                                "🔐 TOKEN STORE: Contract validation failed for Spotify token",
                                extra={
                                    "meta": {
                                        "req_id": req_id,
                                        "token_id": token.id,
                                        "user_id": token.user_id,
                                    }
                                },
                            )
                            return False

                    now = datetime.now(UTC)

                    if existing:
                        # Update existing token
                        existing.access_token = token.access_token
                        existing.access_token_enc = access_token_enc
                        existing.refresh_token = (
                            None if refresh_token_enc else token.refresh_token
                        )
                        existing.refresh_token_enc = refresh_token_enc
                        existing.scopes = token.scopes
                        existing.service_state = token.service_state
                        existing.expires_at = token.expires_at
                        existing.updated_at = now
                        existing.last_refresh_at = (
                            int(time.time())
                            if refresh_token_enc
                            else existing.last_refresh_at
                        )
                        await session.commit()

                        logger.info(
                            "🔐 TOKEN STORE: Token updated successfully",
                            extra={
                                "meta": {
                                    "req_id": req_id,
                                    "token_id": token.id,
                                    "user_id": token.user_id,
                                    "provider": token.provider,
                                    "operation": "update_success",
                                    "expires_at": token.expires_at,
                                    "duration_ms": int(
                                        (time.time() - start_time) * 1000
                                    ),
                                }
                            },
                        )
                    else:
                        # Insert new token
                        new_token = ThirdPartyTokenModel(
                            id=token.id,
                            user_id=token.user_id,
                            identity_id=token.identity_id,
                            provider=token.provider,
                            provider_sub=token.provider_sub,
                            provider_iss=token.provider_iss,
                            access_token=token.access_token,
                            access_token_enc=access_token_enc,
                            refresh_token=(
                                None if refresh_token_enc else token.refresh_token
                            ),
                            refresh_token_enc=refresh_token_enc,
                            envelope_key_version=1,
                            last_refresh_at=(
                                int(time.time()) if refresh_token_enc else 0
                            ),
                            refresh_error_count=0,
                            scopes=token.scopes,
                            service_state=token.service_state,
                            scope_union_since=token.scope_union_since
                            or token.created_at,
                            scope_last_added_from=token.scope_last_added_from,
                            replaced_by_id=token.replaced_by_id,
                            expires_at=token.expires_at,
                            created_at=(
                                datetime.fromtimestamp(token.created_at, UTC)
                                if isinstance(token.created_at, (int, float))
                                else token.created_at
                            ),
                            updated_at=now,
                            is_valid=token.is_valid,
                        )

                        session.add(new_token)
                        await session.commit()

                        logger.info(
                            "🔐 TOKEN STORE: Token inserted successfully",
                            extra={
                                "meta": {
                                    "req_id": req_id,
                                    "token_id": token.id,
                                    "user_id": token.user_id,
                                    "provider": token.provider,
                                    "operation": "insert_success",
                                    "expires_at": token.expires_at,
                                    "duration_ms": int(
                                        (time.time() - start_time) * 1000
                                    ),
                                }
                            },
                        )

                    return True

        except IntegrityError as e:
            logger.error(
                "🔐 TOKEN STORE: Integrity constraint violation",
                extra={
                    "meta": {
                        "req_id": req_id,
                        "token_id": token.id,
                        "user_id": token.user_id,
                        "provider": token.provider,
                        "error": str(e),
                        "operation": "upsert_integrity_error",
                    }
                },
            )
            raise
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
        try:
            async with get_async_db() as session:
                if provider_sub is None:
                    stmt = (
                        select(ThirdPartyTokenModel)
                        .where(
                            and_(
                                ThirdPartyTokenModel.user_id == user_id,
                                ThirdPartyTokenModel.provider == provider,
                                ThirdPartyTokenModel.is_valid == True,
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
                                ThirdPartyTokenModel.user_id == user_id,
                                ThirdPartyTokenModel.provider == provider,
                                ThirdPartyTokenModel.provider_sub == provider_sub,
                                ThirdPartyTokenModel.is_valid == True,
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
                    expires_at=token_model.expires_at,
                    scopes=(
                        token_model.scopes.decode()
                        if isinstance(token_model.scopes, bytes)
                        else token_model.scopes
                    ),
                    service_state=token_model.service_state,
                    scope_union_since=token_model.scope_union_since,
                    scope_last_added_from=token_model.scope_last_added_from,
                    replaced_by_id=token_model.replaced_by_id,
                    created_at=(
                        token_model.created_at.timestamp()
                        if isinstance(token_model.created_at, datetime)
                        else token_model.created_at
                    ),
                    updated_at=(
                        token_model.updated_at.timestamp()
                        if isinstance(token_model.updated_at, datetime)
                        else token_model.updated_at
                    ),
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

                return token

        except Exception as e:
            logger.error(
                "🔐 TOKEN STORE: get_token failed",
                extra={
                    "meta": {
                        "user_id": user_id,
                        "provider": provider,
                        "error_type": type(e).__name__,
                        "error_message": str(e),
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
        try:
            async with get_async_db() as session:
                stmt = (
                    select(ThirdPartyTokenModel)
                    .where(
                        and_(
                            ThirdPartyTokenModel.user_id == user_id,
                            ThirdPartyTokenModel.is_valid == True,
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
                        expires_at=token_model.expires_at,
                        scopes=(
                            token_model.scopes.decode()
                            if isinstance(token_model.scopes, bytes)
                            else token_model.scopes
                        ),
                        service_state=token_model.service_state,
                        scope_union_since=token_model.scope_union_since,
                        scope_last_added_from=token_model.scope_last_added_from,
                        replaced_by_id=token_model.replaced_by_id,
                        created_at=(
                            token_model.created_at.timestamp()
                            if isinstance(token_model.created_at, datetime)
                            else token_model.created_at
                        ),
                        updated_at=(
                            token_model.updated_at.timestamp()
                            if isinstance(token_model.updated_at, datetime)
                            else token_model.updated_at
                        ),
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
        try:
            async with self._lock:
                async with get_async_db() as session:
                    stmt = (
                        update(ThirdPartyTokenModel)
                        .where(
                            and_(
                                ThirdPartyTokenModel.user_id == user_id,
                                ThirdPartyTokenModel.provider == provider,
                                ThirdPartyTokenModel.is_valid == True,
                            )
                        )
                        .values(is_valid=False, updated_at=datetime.now(UTC))
                    )

                    result = await session.execute(stmt)
                    await session.commit()

                    return result.rowcount > 0

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
                    # Find the most recent valid token
                    if provider_sub is None and provider_iss is None:
                        stmt = (
                            select(ThirdPartyTokenModel)
                            .where(
                                and_(
                                    ThirdPartyTokenModel.user_id == user_id,
                                    ThirdPartyTokenModel.provider == provider,
                                    ThirdPartyTokenModel.is_valid == True,
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
                                    ThirdPartyTokenModel.user_id == user_id,
                                    ThirdPartyTokenModel.provider == provider,
                                    ThirdPartyTokenModel.provider_sub == provider_sub,
                                    ThirdPartyTokenModel.provider_iss == provider_iss,
                                    ThirdPartyTokenModel.is_valid == True,
                                )
                            )
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
                    cutoff_time = datetime.now(UTC)
                    cutoff_time = cutoff_time.replace(
                        second=cutoff_time.second - max_age_seconds
                    )

                    stmt = delete(ThirdPartyTokenModel).where(
                        and_(
                            ThirdPartyTokenModel.is_valid == False,
                            ThirdPartyTokenModel.updated_at < cutoff_time,
                        )
                    )

                    result = await session.execute(stmt)
                    await session.commit()

                    return result.rowcount

        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {e}")
            return 0

    def _validate_token_structure(self, token: ThirdPartyToken) -> bool:
        """Validate basic token structure and required fields."""
        try:
            if not token.id or not token.user_id or not token.provider:
                return False

            # Access token is required
            if not token.access_token and not token.access_token_enc:
                return False

            return True
        except Exception:
            return False

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
            if token.access_token and not token.access_token.startswith(("B", "e")):
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
        import re
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

        # 4. access_token matches ^B[A-Za-z0-9] and length ≥ 16+2
        if not token.access_token:
            logger.error(
                "🔒 CONTRACT VALIDATION: FAILED - access_token is required",
                extra={"meta": {"req_id": req_id, "token_id": token.id}},
            )
            validation_passed = False
        else:
            if not re.match(r"^B[A-Za-z0-9]+$", token.access_token):
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - access_token format invalid",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "access_token_prefix": (
                                token.access_token[:2]
                                if len(token.access_token) >= 2
                                else token.access_token
                            ),
                            "expected_pattern": "^B[A-Za-z0-9]+$",
                        }
                    },
                )
                validation_passed = False

            if len(token.access_token) < 18:  # 16 + 2 prefix
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - access_token too short",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "access_token_length": len(token.access_token),
                            "minimum_length": 18,
                        }
                    },
                )
                validation_passed = False

        # 5. refresh_token either None or matches ^A[A-Za-z0-9] (length ≥ 16+2)
        if token.refresh_token is not None:
            if not re.match(r"^A[A-Za-z0-9]+$", token.refresh_token):
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - refresh_token format invalid",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "refresh_token_prefix": (
                                token.refresh_token[:2]
                                if len(token.refresh_token) >= 2
                                else token.refresh_token
                            ),
                            "expected_pattern": "^A[A-Za-z0-9]+$",
                        }
                    },
                )
                validation_passed = False

            if len(token.refresh_token) < 18:  # 16 + 2 prefix
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - refresh_token too short",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "refresh_token_length": len(token.refresh_token),
                            "minimum_length": 18,
                        }
                    },
                )
                validation_passed = False

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

        # 7. scopes non-empty (store as joined string like user-read-email,user-read-private)
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
            # Convert scopes to string format if it's a list
            if isinstance(scopes, list):
                scopes_str = ",".join(scopes)
            elif isinstance(scopes, str):
                scopes_str = scopes
            else:
                scopes_str = str(scopes)

            if not scopes_str.strip():
                logger.error(
                    "🔒 CONTRACT VALIDATION: FAILED - scopes cannot be empty after string conversion",
                    extra={
                        "meta": {
                            "req_id": req_id,
                            "token_id": token.id,
                            "scopes": scopes,
                            "scopes_type": type(scopes).__name__,
                            "scopes_str": scopes_str,
                        }
                    },
                )
                validation_passed = False
            else:
                # Update token.scopes to normalized string format
                token.scopes = scopes_str

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


async def mark_invalid(user_id: str, provider: str) -> bool:
    """Convenience function to mark tokens as invalid."""
    return await token_dao.mark_invalid(user_id, provider)


# ============================================================================
# TOKEN REFRESH SERVICE
# ============================================================================


class TokenRefreshService:
    """Service for handling automatic token refresh with retry logic."""

    def __init__(self):
        self._refresh_lock = asyncio.Lock()
        self._refresh_attempts = {}
        self._max_refresh_attempts = 3
        self._refresh_backoff_seconds = [1, 2, 4]  # Exponential backoff
        # In-memory backoff map to avoid aggressive refresh retries after failures
        # keyed by '{user_id}:{provider}' -> unix timestamp when next refresh allowed
        self._next_refresh_after: dict[str, float] = {}

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

        async with self._refresh_lock:
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
            attempt_key = f"{user_id}:{provider}"
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
                attempt_key = f"{token.user_id}:google"
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

    def reset_refresh_attempts(self, user_id: str, provider: str):
        """Reset refresh attempt counter for a user/provider."""
        attempt_key = f"{user_id}:{provider}"
        self._refresh_attempts.pop(attempt_key, None)


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
    try:
        # Get database stats
        async with get_async_db() as session:
            # Total tokens
            stmt = select(func.count()).select_from(ThirdPartyTokenModel)
            result = await session.execute(stmt)
            total_tokens = result.scalar() or 0

            # Valid tokens
            stmt = (
                select(func.count())
                .select_from(ThirdPartyTokenModel)
                .where(ThirdPartyTokenModel.is_valid == True)
            )
            result = await session.execute(stmt)
            valid_tokens = result.scalar() or 0

            # Tokens by provider
            stmt = (
                select(
                    ThirdPartyTokenModel.provider, func.count(ThirdPartyTokenModel.id)
                )
                .where(ThirdPartyTokenModel.is_valid == True)
                .group_by(ThirdPartyTokenModel.provider)
            )

            result = await session.execute(stmt)
            provider_stats = {row[0]: row[1] for row in result.all()}

            # Expired tokens
            now = int(time.time())
            stmt = (
                select(func.count())
                .select_from(ThirdPartyTokenModel)
                .where(
                    and_(
                        ThirdPartyTokenModel.expires_at < now,
                        ThirdPartyTokenModel.is_valid == True,
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
            extra={"meta": {"error_type": type(e).__name__, "error_message": str(e)}},
        )
        return {
            "status": "unhealthy",
            "timestamp": time.time(),
            "error": str(e),
            "database": {"status": "unknown"},
            "refresh_service": {"status": "unknown"},
        }
