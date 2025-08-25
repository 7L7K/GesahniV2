from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from typing import Optional

from .base import Skill
from app import storage


class DaySummarySkill(Skill):
    PATTERNS = [
        re.compile(r"(today|yesterday|this week) summary", re.I),
        re.compile(r"summary (today|yesterday|week)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        token = match.group(1) if match and match.groups() else "today"
        now = datetime.now()
        if token and token.lower().startswith("yest"):
            start = now - timedelta(days=1)
        elif token and token.lower().startswith("week"):
            start = now - timedelta(days=7)
        else:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Query SQLite ledger for counts since start
        try:
            storage.init_storage()
            cutoff = start.isoformat()
            counts: dict[str, int] = {}
            with storage._conn(storage.LEDGER_DB) as c:
                cur = c.execute(
                    "SELECT type, COUNT(*) as cnt FROM ledger WHERE ts >= ? GROUP BY type",
                    (cutoff,),
                )
                rows = cur.fetchall()
                for r in rows:
                    # sqlite3.Row supports mapping access
                    try:
                        typ = r["type"]
                        cnt = int(r["cnt"])
                    except Exception:
                        typ = r[0]
                        cnt = int(r[1])
                    counts[typ] = cnt
        except Exception:
            return "No events in the requested period."

        if not counts:
            return "No events in the requested period."

        parts = [f"{k}: {v}" for k, v in counts.items()]
        return "; ".join(parts)


__all__ = ["DaySummarySkill"]


