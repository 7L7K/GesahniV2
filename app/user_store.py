"""
PostgreSQL-based user statistics store.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, update

from .db.core import get_async_db
from .db.models import UserStats
from .models.user_stats import UserStats as UserStatsModel


class UserDAO:
    """Data Access Object for user statistics using PostgreSQL."""

    async def get_user_stats(self, user_id: str) -> UserStatsModel:
        """Get user statistics, creating default if not exists."""
        async with get_async_db() as session:
            stmt = select(UserStats).where(UserStats.user_id == user_id)
            result = await session.execute(stmt)
            stats = result.scalar_one_or_none()

            if not stats:
                # Create default stats
                stats = UserStats(user_id=user_id, login_count=0, request_count=0)
                session.add(stats)
                await session.commit()

            return UserStatsModel(
                user_id=stats.user_id,
                login_count=stats.login_count or 0,
                last_login=stats.last_login.isoformat() if stats.last_login else None,
                request_count=stats.request_count or 0,
            )

    async def update_login_stats(self, user_id: str) -> None:
        """Update login count and timestamp."""
        async with get_async_db() as session:
            now = datetime.now(UTC)

            # Try to update existing
            stmt = (
                update(UserStats)
                .where(UserStats.user_id == user_id)
                .values(login_count=UserStats.login_count + 1, last_login=now)
            )
            result = await session.execute(stmt)

            if result.rowcount == 0:
                # Create new record if none existed
                stats = UserStats(
                    user_id=user_id, login_count=1, last_login=now, request_count=0
                )
                session.add(stats)

            await session.commit()

    async def increment_request_count(self, user_id: str) -> None:
        """Increment request count for user."""
        async with get_async_db() as session:
            # Try to update existing
            stmt = (
                update(UserStats)
                .where(UserStats.user_id == user_id)
                .values(request_count=UserStats.request_count + 1)
            )
            result = await session.execute(stmt)

            if result.rowcount == 0:
                # Create new record if none existed
                stats = UserStats(user_id=user_id, login_count=0, request_count=1)
                session.add(stats)

            await session.commit()


# Global instance
user_store = UserDAO()
