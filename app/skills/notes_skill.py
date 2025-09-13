from __future__ import annotations

import re
import sys
from datetime import UTC, datetime

from sqlalchemy import select, delete, func, insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.core import get_async_db
from ..db.models import UserNote, AuthUser
from .base import Skill
from .ledger import record_action


# Default system user ID for notes (since current skill doesn't have user context)
# This is a well-known UUID for the system user
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000001"


class NotesDAO:
    """PostgreSQL-based DAO for user notes."""

    async def _ensure_system_user(self) -> None:
        """Ensure the system user exists in the database."""
        async with get_async_db() as session:
            # Check if system user exists
            stmt = select(AuthUser.id).where(AuthUser.id == SYSTEM_USER_ID)
            result = await session.execute(stmt)
            if result.scalar_one_or_none() is None:
                # Create system user
                system_user = AuthUser(
                    id=SYSTEM_USER_ID,
                    email="system@gesahni.local",
                    password_hash=None,  # No password for system user
                    name="System User",
                    created_at=datetime.now(UTC),
                    verified_at=datetime.now(UTC)
                )
                session.add(system_user)
                await session.commit()

    async def delete_id(self, idx: int) -> None:
        async with get_async_db() as session:
            stmt = delete(UserNote).where(
                UserNote.user_id == SYSTEM_USER_ID,
                UserNote.id == idx
            )
            await session.execute(stmt)
            await session.commit()

    async def delete_text(self, text: str) -> None:
        async with get_async_db() as session:
            stmt = delete(UserNote).where(
                UserNote.user_id == SYSTEM_USER_ID,
                UserNote.text.ilike(f"%{text}%")
            )
            await session.execute(stmt)
            await session.commit()

    async def get(self, idx: int) -> str | None:
        async with get_async_db() as session:
            stmt = select(UserNote.text).where(
                UserNote.user_id == SYSTEM_USER_ID,
                UserNote.id == idx
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            return row

    async def list(self) -> list[tuple[int, str]]:
        async with get_async_db() as session:
            stmt = select(UserNote.id, UserNote.text).where(
                UserNote.user_id == SYSTEM_USER_ID
            ).order_by(UserNote.created_at)
            result = await session.execute(stmt)
            rows = result.fetchall()
            return [(r[0], r[1]) for r in rows]

    async def add(self, text: str) -> None:
        await self._ensure_system_user()
        async with get_async_db() as session:
            note = UserNote(
                user_id=SYSTEM_USER_ID,
                text=text,
                created_at=datetime.now(UTC)
            )
            session.add(note)
            await session.commit()

    async def all_texts(self) -> list[str]:
        async with get_async_db() as session:
            stmt = select(UserNote.text).where(
                UserNote.user_id == SYSTEM_USER_ID
            ).order_by(UserNote.created_at)
            result = await session.execute(stmt)
            rows = result.fetchall()
            return [r[0] for r in rows]

    async def close(self) -> None:
        """No-op for PostgreSQL-based DAO."""
        pass


dao = NotesDAO()


async def close_notes_dao() -> None:
    """Close notes DAO - no-op for PostgreSQL."""
    pass


class NotesSkill(Skill):
    PATTERNS = [
        re.compile(r"delete note (\d+)", re.I),
        re.compile(r"delete note (.+)", re.I),
        re.compile(r"show note (\d+)", re.I),
        re.compile(r"list notes", re.I),
        re.compile(r"show notes", re.I),
        re.compile(r"note (.+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        pat = match.re.pattern
        if pat.startswith("delete note"):
            arg = match.group(1)
            if arg.isdigit():
                await dao.delete_id(int(arg))
                await record_action("notes.delete", idempotency_key=f"notes:delete:{arg}")
            else:
                await dao.delete_text(arg)
                await record_action("notes.delete", idempotency_key=f"notes:delete_text:{arg}")
            return "Deleted."

        if pat.startswith("show note"):
            idx = int(match.group(1))
            row = await dao.get(idx)
            return row if row is not None else "Note not found"

        if pat.startswith("list") or pat.startswith("show notes"):
            rows = await dao.list()
            if not rows:
                return "No notes"
            return "; ".join(f"{rowid}. {text}" for rowid, text in rows)

        if pat.startswith("note"):
            text = match.group(1)
            # idempotency: dedupe within 10s window
            idemp = f"notes:add:{hash(text)}:{int(time.time()//10)}"
            await dao.add(text)
            await record_action("notes.add", idempotency_key=idemp, metadata={"text_len": len(text)})
            return "Noted."

        rows = await dao.all_texts()
        return "; ".join(rows) if rows else "No notes"


# When this module is reloaded (e.g. in tests), ensure the package level
# ``SKILL_CLASSES`` list references the freshly defined class rather than the
# stale copy from the previous import.
try:  # pragma: no cover - best effort hook
    _skills = sys.modules.get("app.skills")
    if _skills:
        classes = getattr(_skills, "SKILL_CLASSES", [])
        for i, cls in enumerate(classes):
            if getattr(cls, "__name__", None) == "NotesSkill":
                classes[i] = NotesSkill
                if i < len(getattr(_skills, "SKILLS", [])):
                    _skills.SKILLS[i] = NotesSkill()
                break
except Exception:
    pass
