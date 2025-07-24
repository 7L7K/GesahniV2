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
        re.compile(r"note (.+)", re.I),
        re.compile(r"show notes", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("note"):
            text = match.group(1)
            conn.execute("INSERT INTO notes (text) VALUES (?)", (text,))
            conn.commit()
            return "Noted."
        rows = [row[0] for row in conn.execute("SELECT text FROM notes").fetchall()]
        return "; ".join(rows) if rows else "No notes"
