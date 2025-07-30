from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

from .base import Skill

DB_PATH = Path(os.getenv("NOTES_DB", "notes.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.execute(
    "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)"
)
conn.commit()


class NotesSkill(Skill):
    PATTERNS = [
        re.compile(r"note (.+)", re.I),
        re.compile(r"(?:show|list) notes", re.I),
        re.compile(r"show note (\d+)", re.I),
        re.compile(r"delete note (.+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        pat = match.re.pattern
        if pat.startswith("note"):
            text = match.group(1)
            conn.execute("INSERT INTO notes (text) VALUES (?)", (text,))
            conn.commit()
            return "Noted."
        if "show note" in pat:
            idx = int(match.group(1))
            row = conn.execute("SELECT text FROM notes WHERE id=?", (idx,)).fetchone()
            return row[0] if row else "Not found"
        if "delete note" in pat:
            target = match.group(1).strip()
            if target.isdigit():
                conn.execute("DELETE FROM notes WHERE id=?", (int(target),))
            else:
                conn.execute("DELETE FROM notes WHERE text LIKE ?", (f"%{target}%",))
            conn.commit()
            return "Deleted."
        rows = [f"{row[0]}) {row[1]}" for row in conn.execute("SELECT id, text FROM notes").fetchall()]
        return "; ".join(rows) if rows else "No notes"
