"""
PostgreSQL-based user statistics store.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select, text, update

from app.db.core import get_async_session
from app.db.models import UserStats
from app.models.user_stats import UserStats as UserStatsModel
from app.util.ids import to_uuid


class UserDAO:
    """Data Access Object for user statistics using PostgreSQL."""

    async def get_user_stats(self, user_id: str) -> UserStatsModel:
        """Get user statistics, creating default if not exists."""
        user_uuid = str(to_uuid(user_id))

        async with get_async_session() as session:
            stmt = select(UserStats).where(UserStats.user_id == user_uuid)
            result = await session.execute(stmt)
            stats = result.scalar_one_or_none()

            created_default = False
            if not stats:
                stats = UserStats(
                    user_id=user_uuid,
                    login_count=0,
                    request_count=0,
                )
                session.add(stats)
                await session.commit()
                created_default = True

            if created_default:
                # Refresh to pick up defaults like updated_at
                await session.refresh(stats)

            return UserStatsModel(
                user_id=stats.user_id,
                login_count=stats.login_count or 0,
                last_login=stats.last_login.isoformat() if stats.last_login else None,
                request_count=stats.request_count or 0,
            )

    async def update_login_stats(self, user_id: str) -> None:
        """Update login count and timestamp."""
        user_uuid = str(to_uuid(user_id))
        now = datetime.now(UTC)

        async with get_async_session() as session:
            stmt = (
                update(UserStats)
                .where(UserStats.user_id == user_uuid)
                .values(
                    login_count=UserStats.login_count + 1,
                    last_login=now,
                    updated_at=now,
                )
            )
            result = await session.execute(stmt)

            if result.rowcount == 0:
                stats = UserStats(
                    user_id=user_uuid,
                    login_count=1,
                    last_login=now,
                    request_count=0,
                    updated_at=now,
                )
                session.add(stats)

            await session.commit()

    async def increment_login(self, user_id: str) -> None:
        """Increment login count and update timestamp. Alias for update_login_stats."""
        await self.update_login_stats(user_id)

    async def increment_request_count(self, user_id: str) -> None:
        """Increment request count for user."""
        user_uuid = str(to_uuid(user_id))
        now = datetime.now(UTC)

        async with get_async_session() as session:
            stmt = (
                update(UserStats)
                .where(UserStats.user_id == user_uuid)
                .values(
                    request_count=UserStats.request_count + 1,
                    updated_at=now,
                )
            )
            result = await session.execute(stmt)

            if result.rowcount == 0:
                stats = UserStats(
                    user_id=user_uuid,
                    login_count=0,
                    request_count=1,
                    updated_at=now,
                )
                session.add(stats)

            await session.commit()

    async def ensure_user(self, user_id: str) -> None:
        """Ensure a user record exists, creating it if necessary."""
        user_uuid = str(to_uuid(user_id))
        username = f"anon_{user_uuid.replace('-', '')}"[:100]
        email = f"{user_uuid}@local.test"

        async with get_async_session() as session:
            insert_user = text(
                """
                INSERT INTO auth.users (id, email, username, name, created_at)
                VALUES (CAST(:id AS uuid), :email, :username, :name, now())
                ON CONFLICT (id) DO NOTHING
                """
            )
            await session.execute(
                insert_user,
                {
                    "id": user_uuid,
                    "email": email,
                    "username": username,
                    "name": f"Guest {username}",
                },
            )

            insert_stats = text(
                """
                INSERT INTO users.user_stats (user_id, login_count, last_login, request_count)
                VALUES (CAST(:id AS uuid), 0, NULL, 0)
                ON CONFLICT (user_id) DO NOTHING
                """
            )
            await session.execute(insert_stats, {"id": user_uuid})

            await session.commit()


# Global instance
user_store = UserDAO()
