"""
PostgreSQL-based user statistics store.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from .db.core import get_async_db
from .db.models import UserStats
from .models.user_stats import UserStats as UserStatsModel
from .util.ids import to_uuid


class UserDAO:
    """Data Access Object for user statistics using PostgreSQL."""

    async def get_user_stats(self, user_id: str) -> UserStatsModel:
        """Get user statistics, creating default if not exists."""
        session_gen = get_async_db()
        session = await anext(session_gen)  # Get the session from the async generator
        try:
            stmt = select(UserStats).where(UserStats.user_id == str(to_uuid(user_id)))
            result = await session.execute(stmt)
            stats = result.scalar_one_or_none()

            if not stats:
                # Create default stats
                stats = UserStats(
                    user_id=str(to_uuid(user_id)), login_count=0, request_count=0
                )
                session.add(stats)
                await session.commit()

            return UserStatsModel(
                user_id=stats.user_id,
                login_count=stats.login_count or 0,
                last_login=stats.last_login.isoformat() if stats.last_login else None,
                request_count=stats.request_count or 0,
            )
        finally:
            await session.close()

    async def update_login_stats(self, user_id: str) -> None:
        """Update login count and timestamp."""
        session_gen = get_async_db()
        session = await anext(session_gen)  # Get the session from the async generator
        try:
            now = datetime.now(UTC)

            # Try to update existing
            stmt = (
                update(UserStats)
                .where(UserStats.user_id == str(to_uuid(user_id)))
                .values(login_count=UserStats.login_count + 1, last_login=now)
            )
            result = await session.execute(stmt)

            if result.rowcount == 0:
                # Create new record if none existed
                stats = UserStats(
                    user_id=str(to_uuid(user_id)),
                    login_count=1,
                    last_login=now,
                    request_count=0,
                )
                session.add(stats)

            await session.commit()
        finally:
            await session.close()

    async def increment_request_count(self, user_id: str) -> None:
        """Increment request count for user."""
        session_gen = get_async_db()
        session = await anext(session_gen)  # Get the session from the async generator
        try:
            # Try to update existing
            stmt = (
                update(UserStats)
                .where(UserStats.user_id == str(to_uuid(user_id)))
                .values(request_count=UserStats.request_count + 1)
            )
            result = await session.execute(stmt)

            if result.rowcount == 0:
                # Create new record if none existed
                stats = UserStats(
                    user_id=str(to_uuid(user_id)), login_count=0, request_count=1
                )
                session.add(stats)

            await session.commit()
        finally:
            await session.close()

    async def ensure_user(self, user_id: str) -> None:
        """Ensure a user record exists, creating it if necessary."""
        session_gen = get_async_db()
        session = await anext(session_gen)  # Get the session from the async generator
        try:
            stmt = select(UserStats).where(UserStats.user_id == str(to_uuid(user_id)))
            result = await session.execute(stmt)
            stats = result.scalar_one_or_none()

            if not stats:
                # Create default stats
                stats = UserStats(
                    user_id=str(to_uuid(user_id)), login_count=0, request_count=0
                )
                session.add(stats)
                await session.commit()
        finally:
            await session.close()


# Global instance
user_store = UserDAO()
