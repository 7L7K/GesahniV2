#!/usr/bin/env python3
"""Weekly job to age-out stale third-party tokens.

Marks tokens invalid if no successful refresh or probe in the last 30 days.
Run via cron or scheduler once per week.
"""
import sqlite3
import time
from pathlib import Path

DB = Path("third_party_tokens.db")
THIRTY_DAYS = 30 * 24 * 3600


def main():
    if not DB.exists():
        print("DB not found, skipping")
        return
    now = int(time.time())
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    # tokens considered stale if updated_at or last_refresh_at older than threshold
    cutoff = now - THIRTY_DAYS
    cur.execute(
        "SELECT id, user_id, provider, last_refresh_at, updated_at FROM third_party_tokens WHERE is_valid = 1"
    )
    rows = cur.fetchall()
    stale = []
    for r in rows:
        tid, uid, provider, last_refresh_at, updated_at = r
        last = max(int(last_refresh_at or 0), int(updated_at or 0))
        if last < cutoff:
            stale.append((tid, uid, provider))

    for tid, uid, provider in stale:
        print(f"Invalidating stale token: {tid} ({uid}/{provider})")
        cur.execute(
            "UPDATE third_party_tokens SET is_valid = 0, updated_at = ? WHERE id = ?",
            (now, tid),
        )

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
