from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from .base import Skill

DB_PATH = Path(os.getenv("NOTES_DB", "notes.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.execute("CREATE TABLE IF NOT EXISTS notes (text TEXT)")
conn.commit()


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
                conn.execute("DELETE FROM notes WHERE rowid=?", (int(arg),))
            else:
                conn.execute("DELETE FROM notes WHERE text LIKE ?", (f"%{arg}%",))
            conn.commit()
            return "Deleted."

        if pat.startswith("show note"):
            idx = int(match.group(1))
            row = conn.execute("SELECT text FROM notes WHERE rowid=?", (idx,)).fetchone()
            return row[0] if row else "Note not found"

        if pat.startswith("list") or pat.startswith("show notes"):
            rows = [(r[0], r[1]) for r in conn.execute("SELECT rowid, text FROM notes").fetchall()]
            if not rows:
                return "No notes"
            return "; ".join(f"{rowid}. {text}" for rowid, text in rows)

        if pat.startswith("note"):
            text = match.group(1)
            conn.execute("INSERT INTO notes (text) VALUES (?)", (text,))
            conn.commit()
            return "Noted."

        rows = [row[0] for row in conn.execute("SELECT text FROM notes").fetchall()]
        return "; ".join(rows) if rows else "No notes"
