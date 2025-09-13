from __future__ import annotations

"""User model using PostgreSQL through app.db.core (Phase 3 conversion).

Converted from sqlite3 to PostgreSQL for consistency with Phase 3 requirements.
All database access now goes through app.db.core.
"""

from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.core import get_async_db
from app.db.models import AuthUser

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class User:
    id: int | None
    username: str
    hashed_password: str
    login_count: int = 0
    last_login: datetime | None = None


# ---------------------------------------------------------------------------
# Database operations using PostgreSQL through app.db.core
# ---------------------------------------------------------------------------


def init_db() -> None:
    """No-op initialiser kept for API compatibility."""


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session from app.db.core."""
    async with get_async_db() as session:
        yield session


async def create_user_async(username: str, hashed_password: str) -> User:
    """Create a new user asynchronously using PostgreSQL."""
    async for session in get_async_db():
        # Create user using SQLAlchemy model
        user = AuthUser(
            username=username,
            email=f"{username}@local.test",
            password_hash=hashed_password,
            name=username,
            created_at=datetime.now(UTC)
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        return User(
            id=user.id,
            username=user.username,
            hashed_password=user.password_hash,
            login_count=0,
            last_login=None,
        )


async def get_user_async(username: str) -> User | None:
    """Get a user by username asynchronously using PostgreSQL."""
    async for session in get_async_db():
        stmt = select(AuthUser).where(AuthUser.username == username)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            return User(
                id=user.id,
                username=user.username,
                hashed_password=user.password_hash,
                login_count=0,
                last_login=None,
            )
        return None


async def list_users_async() -> Iterable[User]:
    """List all users asynchronously using PostgreSQL."""
    async for session in get_async_db():
        result = await session.execute(
            text("""
                SELECT id, username, password_hash, created_at
                FROM auth.users
                ORDER BY created_at DESC
            """)
        )
        users = []
        for row in result:
            users.append(User(
                id=row[0],
                username=row[1],
                hashed_password=row[2],
                login_count=0,
                last_login=None,
            ))
        return users


async def update_login_async(user: User) -> User:
    """Update user login count and timestamp asynchronously."""
    user.login_count += 1
    user.last_login = datetime.now(UTC)

    async for session in get_async_db():
        # Update login count in users.stats if it exists
        await session.execute(
            text("""
                INSERT INTO users.user_stats (user_id, login_count, last_login)
                VALUES (:user_id, :count, :last_login)
                ON CONFLICT (user_id) DO UPDATE SET
                    login_count = EXCLUDED.login_count,
                    last_login = EXCLUDED.last_login
            """),
            {
                "user_id": user.id,
                "count": user.login_count,
                "last_login": user.last_login,
            }
        )
        await session.commit()

    return user


async def delete_user_async(user: User) -> None:
    """Delete a user asynchronously."""
    if user.id is None:
        return

    async for session in get_async_db():
        await session.execute(
            text("DELETE FROM auth.users WHERE id = :user_id"),
            {"user_id": user.id}
        )
        await session.commit()


# Legacy synchronous wrappers for backward compatibility
# These will raise errors to force conversion to async

def get_session():
    """Deprecated: Use get_async_session() instead."""
    raise RuntimeError("SQLite synchronous operations are deprecated. Use async PostgreSQL operations.")


def create_user(db, username: str, hashed_password: str) -> User:
    """Deprecated: Use create_user_async() instead."""
    raise RuntimeError("SQLite operations are deprecated. Use async PostgreSQL operations.")


def get_user(db, username: str) -> User | None:
    """Deprecated: Use get_user_async() instead."""
    raise RuntimeError("SQLite operations are deprecated. Use async PostgreSQL operations.")


def list_users(db) -> Iterable[User]:
    """Deprecated: Use list_users_async() instead."""
    raise RuntimeError("SQLite operations are deprecated. Use async PostgreSQL operations.")


def update_login(db, user: User) -> User:
    """Deprecated: Use update_login_async() instead."""
    raise RuntimeError("SQLite operations are deprecated. Use async PostgreSQL operations.")


def delete_user(db, user: User) -> None:
    """Deprecated: Use delete_user_async() instead."""
    raise RuntimeError("SQLite operations are deprecated. Use async PostgreSQL operations.")


__all__ = [
    "User",
    "init_db",
    "get_async_session",
    "create_user_async",
    "get_user_async",
    "list_users_async",
    "update_login_async",
    "delete_user_async",
    # Legacy synchronous functions (deprecated)
    "get_session",
    "create_user",
    "get_user",
    "list_users",
    "update_login",
    "delete_user",
]
