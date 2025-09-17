"""
PostgreSQL-based authentication store.

This module provides user, device, session, and OAuth identity management
using PostgreSQL and SQLAlchemy ORM.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from .db.core import get_async_db
from .db.models import (
    AuditLog,
    AuthDevice,
    AuthIdentity,
    AuthUser,
    PATToken,
    Session,
)


def _now() -> datetime:
    return datetime.now(UTC)


def _db_path() -> str:
    """Get the database path for backward compatibility.

    This function is kept for backward compatibility with tests that expect
    a SQLite database path. Since this module now uses PostgreSQL, this
    returns a default SQLite path for testing purposes.
    """
    import os
    from pathlib import Path

    # Check for environment override first
    env_path = os.getenv("USERS_DB")
    if env_path:
        return env_path

    # Default to a test database path
    return str(Path(__file__).parent.parent / "users.db")


async def ensure_tables() -> None:
    """PostgreSQL schema is managed by migrations, no runtime table creation needed."""
    pass


# ------------------------------ users ----------------------------------------
async def create_user(
    *,
    id: str,
    email: str,
    password_hash: str | None = None,
    name: str | None = None,
    avatar_url: str | None = None,
    auth_providers: list[str] | None = None,
    username: str | None = None,
) -> None:
    """Create or upsert a user, honoring the provided id."""
    async with get_async_db() as session:
        norm_email = (email or "").strip().lower()
        json.dumps(auth_providers or [])

        # Check for existing user by email
        stmt = select(AuthUser).where(AuthUser.email == norm_email)
        result = await session.execute(stmt)
        existing_user = result.scalar_one_or_none()

        if existing_user is None:
            # Create new user
            user = AuthUser(
                id=id,
                email=norm_email,
                password_hash=password_hash,
                name=name,
                avatar_url=avatar_url,
                username=username,
                created_at=_now(),
            )
            session.add(user)
        else:
            # Update existing user
            existing_user.password_hash = password_hash or existing_user.password_hash
            existing_user.name = name or existing_user.name
            existing_user.avatar_url = avatar_url or existing_user.avatar_url
            existing_user.username = username or existing_user.username

        await session.commit()


async def get_user_by_email(email: str) -> dict[str, Any] | None:
    async with get_async_db() as session:
        norm_email = (email or "").strip().lower()
        stmt = select(AuthUser).where(AuthUser.email == norm_email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            return None

        return {
            "id": user.id,
            "email": user.email,
            "password_hash": user.password_hash,
            "name": user.name,
            "avatar_url": user.avatar_url,
            "created_at": (
                user.created_at.timestamp()
                if isinstance(user.created_at, datetime)
                else user.created_at
            ),
            "verified_at": (
                user.verified_at.timestamp()
                if user.verified_at and isinstance(user.verified_at, datetime)
                else user.verified_at
            ),
            "auth_providers": [],  # TODO: Add auth_providers field to model if needed
        }


async def verify_user(user_id: str) -> None:
    async with get_async_db() as session:
        stmt = update(AuthUser).where(AuthUser.id == user_id).values(verified_at=_now())
        await session.execute(stmt)
        await session.commit()


# ----------------------------- devices ---------------------------------------
async def create_device(
    *, id: str, user_id: str, device_name: str | None, ua_hash: str, ip_hash: str
) -> None:
    async with get_async_db() as session:
        device = AuthDevice(
            id=id,
            user_id=user_id,
            device_name=device_name,
            ua_hash=ua_hash,
            ip_hash=ip_hash,
            created_at=_now(),
            last_seen_at=_now(),
        )
        session.add(device)
        await session.commit()


async def touch_device(device_id: str) -> None:
    async with get_async_db() as session:
        stmt = (
            update(AuthDevice)
            .where(AuthDevice.id == device_id)
            .values(last_seen_at=_now())
        )
        await session.execute(stmt)
        await session.commit()


# ----------------------------- sessions --------------------------------------
async def create_session(
    *, id: str, user_id: str, device_id: str, mfa_passed: bool = False
) -> None:
    async with get_async_db() as session:
        session_obj = Session(
            id=id,
            user_id=user_id,
            device_id=device_id,
            created_at=_now(),
            last_seen_at=_now(),
            mfa_passed=mfa_passed,
        )
        session.add(session_obj)
        await session.commit()


async def touch_session(session_id: str) -> None:
    async with get_async_db() as session:
        stmt = (
            update(Session).where(Session.id == session_id).values(last_seen_at=_now())
        )
        await session.execute(stmt)
        await session.commit()


async def revoke_session(session_id: str) -> None:
    async with get_async_db() as session:
        stmt = update(Session).where(Session.id == session_id).values(revoked_at=_now())
        await session.execute(stmt)
        await session.commit()


# ------------------------- oauth identities ----------------------------------
async def link_oauth_identity(
    *,
    id: str,
    user_id: str,
    provider: str,
    provider_sub: str,
    email_normalized: str,
    provider_iss: str | None = None,
    email_verified: bool = False,
) -> None:
    async with get_async_db() as session:
        identity = AuthIdentity(
            id=id,
            user_id=user_id,
            provider=provider,
            provider_iss=provider_iss,
            provider_sub=provider_sub,
            email_normalized=email_normalized,
            email_verified=email_verified,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(identity)
        await session.commit()


async def get_oauth_identity_by_provider(
    provider: str, provider_iss: str | None, provider_sub: str
) -> dict | None:
    """Return oauth identity row by provider+iss+provider_sub or None."""
    async with get_async_db() as session:
        stmt = select(AuthIdentity).where(
            AuthIdentity.provider == provider,
            AuthIdentity.provider_sub == provider_sub,
            AuthIdentity.provider_iss == provider_iss,
        )
        result = await session.execute(stmt)
        identity = result.scalar_one_or_none()

        if not identity:
            return None

        return {
            "id": identity.id,
            "user_id": identity.user_id,
            "provider": identity.provider,
            "provider_iss": identity.provider_iss,
            "provider_sub": identity.provider_sub,
            "email_normalized": identity.email_normalized,
            "email_verified": identity.email_verified,
            "created_at": (
                identity.created_at.timestamp()
                if isinstance(identity.created_at, datetime)
                else identity.created_at
            ),
            "updated_at": (
                identity.updated_at.timestamp()
                if isinstance(identity.updated_at, datetime)
                else identity.updated_at
            ),
        }


async def get_oauth_identity_by_provider_simple(
    provider: str, provider_sub: str
) -> dict | None:
    """Return oauth identity row by provider+provider_sub or None."""
    async with get_async_db() as session:
        stmt = select(AuthIdentity).where(
            AuthIdentity.provider == provider,
            AuthIdentity.provider_sub == provider_sub,
        )
        result = await session.execute(stmt)
        identity = result.scalar_one_or_none()

        if not identity:
            return None

        return {
            "id": identity.id,
            "user_id": identity.user_id,
            "provider": identity.provider,
            "provider_sub": identity.provider_sub,
            "email_normalized": identity.email_normalized,
            "email_verified": identity.email_verified,
            "created_at": (
                identity.created_at.timestamp()
                if isinstance(identity.created_at, datetime)
                else identity.created_at
            ),
            "updated_at": (
                identity.updated_at.timestamp()
                if isinstance(identity.updated_at, datetime)
                else identity.updated_at
            ),
        }


async def get_user_id_by_identity_id(identity_id: str) -> str | None:
    """Return user_id for the given identity_id or None."""
    async with get_async_db() as session:
        stmt = select(AuthIdentity.user_id).where(AuthIdentity.id == identity_id)
        result = await session.execute(stmt)
        user_id = result.scalar_one_or_none()
        return user_id


# ---------------------------- PAT tokens -------------------------------------
async def create_pat(
    *,
    id: str,
    user_id: str,
    name: str,
    token_hash: str,
    scopes: list[str],
    exp_at: float | None = None,
) -> None:
    async with get_async_db() as session:
        pat = PATToken(
            id=id,
            user_id=user_id,
            name=name,
            token_hash=token_hash,
            scopes=json.dumps(scopes or []),
            exp_at=datetime.fromtimestamp(exp_at, UTC) if exp_at else None,
            created_at=_now(),
        )
        session.add(pat)
        await session.commit()


async def revoke_pat(pat_id: str) -> None:
    async with get_async_db() as session:
        stmt = update(PATToken).where(PATToken.id == pat_id).values(revoked_at=_now())
        await session.execute(stmt)
        await session.commit()


async def get_pat_by_id(pat_id: str) -> dict[str, Any] | None:
    async with get_async_db() as session:
        stmt = select(PATToken).where(PATToken.id == pat_id)
        result = await session.execute(stmt)
        pat = result.scalar_one_or_none()

        if not pat:
            return None

        return {
            "id": pat.id,
            "user_id": pat.user_id,
            "name": pat.name,
            "token_hash": pat.token_hash,
            "scopes": json.loads(pat.scopes) if pat.scopes else [],
            "exp_at": (
                pat.exp_at.timestamp()
                if pat.exp_at and isinstance(pat.exp_at, datetime)
                else pat.exp_at
            ),
            "created_at": (
                pat.created_at.timestamp()
                if isinstance(pat.created_at, datetime)
                else pat.created_at
            ),
            "revoked_at": (
                pat.revoked_at.timestamp()
                if pat.revoked_at and isinstance(pat.revoked_at, datetime)
                else pat.revoked_at
            ),
        }


async def get_pat_by_hash(token_hash: str) -> dict[str, Any] | None:
    async with get_async_db() as session:
        stmt = select(PATToken).where(PATToken.token_hash == token_hash)
        result = await session.execute(stmt)
        pat = result.scalar_one_or_none()

        if not pat:
            return None

        return {
            "id": pat.id,
            "user_id": pat.user_id,
            "name": pat.name,
            "token_hash": pat.token_hash,
            "scopes": json.loads(pat.scopes) if pat.scopes else [],
            "exp_at": (
                pat.exp_at.timestamp()
                if pat.exp_at and isinstance(pat.exp_at, datetime)
                else pat.exp_at
            ),
            "created_at": (
                pat.created_at.timestamp()
                if isinstance(pat.created_at, datetime)
                else pat.created_at
            ),
            "revoked_at": (
                pat.revoked_at.timestamp()
                if pat.revoked_at and isinstance(pat.revoked_at, datetime)
                else pat.revoked_at
            ),
        }


async def list_pats_for_user(user_id: str) -> list[dict[str, Any]]:
    """List all PATs for a user, returning safe fields only (no token hash)."""
    async with get_async_db() as session:
        stmt = (
            select(PATToken)
            .where(PATToken.user_id == user_id)
            .order_by(PATToken.created_at.desc())
        )
        result = await session.execute(stmt)
        pats = result.scalars().all()

        return [
            {
                "id": pat.id,
                "name": pat.name,
                "scopes": json.loads(pat.scopes) if pat.scopes else [],
                "created_at": (
                    pat.created_at.timestamp()
                    if isinstance(pat.created_at, datetime)
                    else pat.created_at
                ),
                "revoked_at": (
                    pat.revoked_at.timestamp()
                    if pat.revoked_at and isinstance(pat.revoked_at, datetime)
                    else pat.revoked_at
                ),
            }
            for pat in pats
        ]


# ---------------------------- audit log --------------------------------------
async def record_audit(
    *,
    id: str,
    user_id: str | None,
    session_id: str | None,
    event_type: str,
    meta: dict[str, Any] | None = None,
) -> None:
    async with get_async_db() as session:
        audit = AuditLog(
            id=id,
            user_id=user_id,
            session_id=session_id,
            event_type=event_type,
            meta=json.dumps(meta or {}),
            created_at=_now(),
        )
        session.add(audit)
        await session.commit()


__all__ = [
    "_db_path",
    "ensure_tables",
    # users
    "create_user",
    "get_user_by_email",
    "verify_user",
    # devices
    "create_device",
    "touch_device",
    # sessions
    "create_session",
    "touch_session",
    "revoke_session",
    # oauth
    "link_oauth_identity",
    # pat
    "create_pat",
    "revoke_pat",
    "get_pat_by_hash",
    "get_pat_by_id",
    "list_pats_for_user",
    # audit
    "record_audit",
]
