"""DB utilities for tests."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


async def truncate_all_tables(
    engine: AsyncEngine, *, schema: str = "public", exclude: Iterable[str] | None = None
) -> None:
    """Truncate all tables in the given schema.

    Useful when a test needs a hard reset beyond transaction rollback.
    """
    excludes = set(exclude or [])
    async with engine.connect() as conn:
        res = await conn.execute(
            text(
                """
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = :schema
                """
            ),
            {"schema": schema},
        )
        tables = [r[0] for r in res if r[0] not in excludes]
        if tables:
            await conn.execute(text("SET session_replication_role = 'replica'"))
            try:
                await conn.execute(
                    text(
                        "TRUNCATE TABLE "
                        + ",".join(f'"{t}"' for t in tables)
                        + " RESTART IDENTITY CASCADE"
                    )
                )
            finally:
                await conn.execute(text("SET session_replication_role = 'origin'"))
        await conn.commit()
