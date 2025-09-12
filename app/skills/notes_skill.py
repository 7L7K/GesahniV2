from __future__ import annotations

import re
import sys
from pathlib import Path

import aiosqlite

from ..db.paths import resolve_db_path
from .base import Skill
from .ledger import record_action


def _db_path() -> Path:
    p = resolve_db_path("NOTES_DB", "notes.db")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


class NotesDAO:
    def __init__(self, path: Path):
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._path)
            await self._conn.execute("CREATE TABLE IF NOT EXISTS notes (text TEXT)")
            await self._conn.commit()
        return self._conn

    async def delete_id(self, idx: int) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM notes WHERE rowid=?", (idx,))
        await conn.commit()

    async def delete_text(self, text: str) -> None:
        conn = await self._get_conn()
        await conn.execute("DELETE FROM notes WHERE text LIKE ?", (f"%{text}%",))
        await conn.commit()

    async def get(self, idx: int) -> str | None:
        conn = await self._get_conn()
        async with conn.execute("SELECT text FROM notes WHERE rowid=?", (idx,)) as cur:
            row = await cur.fetchone()
        return row[0] if row else None

    async def list(self) -> list[tuple[int, str]]:
        conn = await self._get_conn()
        async with conn.execute("SELECT rowid, text FROM notes") as cur:
            rows = await cur.fetchall()
        return [(r[0], r[1]) for r in rows]

    async def add(self, text: str) -> None:
        conn = await self._get_conn()
        await conn.execute("INSERT INTO notes (text) VALUES (?)", (text,))
        await conn.commit()

    async def all_texts(self) -> list[str]:
        conn = await self._get_conn()
        async with conn.execute("SELECT text FROM notes") as cur:
            rows = await cur.fetchall()
        return [r[0] for r in rows]

    async def close(self) -> None:
        """Close persistent aiosqlite connection if open."""
        conn = getattr(self, "_conn", None)
        if conn is not None:
            try:
                await conn.close()
            except Exception:
                pass
            self._conn = None


dao = NotesDAO(_db_path())


async def close_notes_dao() -> None:
    try:
        await dao.close()
    except Exception:
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
