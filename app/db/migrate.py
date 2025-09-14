"""Database migration orchestration system.

Provides a centralized way to run all schema migrations for the application.
Safe to call from startup, tests, and manual operations.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Raised when a migration fails."""

    pass


async def run_all_migrations(db_dir: Path | None = None) -> None:
    """Run all database schema migrations.

    Args:
        db_dir: Optional directory containing database files.
                If None, uses default database locations.

    Raises:
        MigrationError: If any migration fails
    """
    logger.info(
        "Starting database migrations",
        extra={"db_dir": str(db_dir) if db_dir else None},
    )

    migration_tasks: list[Callable[[], Awaitable[None]]] = []

    # Token store migration
    async def migrate_token_store():
        try:
            from app.auth_store_tokens import TokenDAO

            dao = TokenDAO(str(db_dir / "third_party_tokens.db") if db_dir else None)
            await dao.ensure_schema_migrated()
            logger.info("Token store migration completed")
        except Exception as e:
            logger.error("Token store migration failed", exc_info=True)
            raise MigrationError(f"Token store migration failed: {e}")

    # User store migration
    async def migrate_user_store():
        try:
            if db_dir:
                from app.user_store import UserDAO

                user_dao = UserDAO(db_dir / "users.db")
            else:
                from app.user_store import user_dao
            await user_dao.ensure_schema_migrated()
            logger.info("User store migration completed")
        except Exception as e:
            logger.error("User store migration failed", exc_info=True)
            raise MigrationError(f"User store migration failed: {e}")

    # Add all migration tasks
    migration_tasks.extend(
        [
            migrate_token_store,
            migrate_user_store,
        ]
    )

    # Run all migrations concurrently but safely
    for task in migration_tasks:
        try:
            await task()
        except MigrationError:
            raise  # Re-raise migration errors
        except Exception as e:
            logger.error(f"Migration task failed: {e}", exc_info=True)
            raise MigrationError(f"Migration task failed: {e}")

    logger.info("All database migrations completed successfully")


async def ensure_all_schemas_migrated() -> None:
    """Ensure all database schemas are migrated.

    Called during application startup to guarantee database readiness.
    """
    try:
        await run_all_migrations()
    except MigrationError as e:
        logger.error(f"Database migration failed during startup: {e}")
        # In production, you might want to raise this to prevent startup
        # For development, we'll log and continue
        if __name__ != "__main__":  # Not called as script
            raise


# CLI interface for manual migrations
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 2:
        print("Usage: python -m app.db.migrate [db_dir]")
        sys.exit(1)

    db_dir = Path(sys.argv[1]) if len(sys.argv) == 2 else None

    # Set up basic logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Run migrations
    try:
        asyncio.run(run_all_migrations(db_dir))
        print("✅ All migrations completed successfully")
    except MigrationError as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)
