from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import text

from app.db.core import sync_engine

from .base import Skill


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

        # Query PostgreSQL ledger for counts since start using app.db.core
        try:
            cutoff = start.isoformat()
            counts: dict[str, int] = {}
            with sync_engine.connect() as conn:
                result = conn.execute(
                    text(
                        """
                        SELECT operation as type, COUNT(*) as cnt
                        FROM storage.ledger
                        WHERE created_at >= :cutoff::timestamptz
                        GROUP BY operation
                    """
                    ),
                    {"cutoff": cutoff},
                )
                for row in result.mappings():
                    typ = row["type"]
                    cnt = int(row["cnt"])
                    counts[typ] = cnt
        except Exception:
            return "No events in the requested period."

        if not counts:
            return "No events in the requested period."

        parts = [f"{k}: {v}" for k, v in counts.items()]
        return "; ".join(parts)


__all__ = ["DaySummarySkill"]
