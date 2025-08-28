from __future__ import annotations

import asyncio
import logging
import os
import random
import sqlite3
import time
from typing import List, Tuple

from ..integrations.google.oauth import refresh_token
from ..metrics import SPOTIFY_REFRESH, SPOTIFY_REFRESH_ERROR, GOOGLE_REFRESH_SUCCESS, GOOGLE_REFRESH_FAILED

logger = logging.getLogger(__name__)

# Threshold in seconds before expiry to proactively refresh
REFRESH_AHEAD_SECONDS = int(os.getenv("GOOGLE_REFRESH_AHEAD_SECONDS", "300"))

# Path to tokens DB
DB_PATH = os.getenv("THIRD_PARTY_TOKENS_DB", "third_party_tokens.db")


def _get_candidates(now: int) -> List[Tuple[str, str, int]]:
    out = []
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cutoff = now + REFRESH_AHEAD_SECONDS
        cur.execute(
            """
            SELECT user_id, provider, expires_at
            FROM third_party_tokens
            WHERE is_valid = 1 AND expires_at <= ? AND provider = 'google'
            GROUP BY user_id, provider
            """,
            (cutoff,),
        )
        rows = cur.fetchall()
        for r in rows:
            out.append((r[0], r[1], int(r[2] or 0)))
    finally:
        conn.close()
    return out


async def _refresh_for_user(user_id: str, provider: str) -> None:
    attempt = 0
    max_attempts = 3
    base_delay = 1.0

    while attempt < max_attempts:
        attempt += 1
        try:
            # Fetch latest token row
            conn = sqlite3.connect(DB_PATH)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, refresh_token FROM third_party_tokens WHERE user_id = ? AND provider = ? AND is_valid = 1 ORDER BY created_at DESC LIMIT 1",
                    (user_id, provider),
                )
                row = cur.fetchone()
                if not row:
                    return
                token_id, refresh_tok = row[0], row[1]
            finally:
                conn.close()

            if not refresh_tok:
                raise RuntimeError("no_refresh_token")

            td = await refresh_token(refresh_tok)

            # Persist new token row using direct DB write to mirror auth_store_tokens.upsert
            now = int(time.time())
            expires_at = int(td.get("expires_at", now + int(td.get("expires_in", 3600))))
            new_id = f"google:{secrets.token_hex(8)}"
            conn = sqlite3.connect(DB_PATH)
            try:
                cur = conn.cursor()
                # Mark previous valid tokens invalid
                cur.execute("UPDATE third_party_tokens SET is_valid = 0, updated_at = ? WHERE user_id = ? AND provider = ? AND is_valid = 1", (now, user_id, provider))
                cur.execute(
                    "INSERT INTO third_party_tokens (id, user_id, provider, access_token, refresh_token, scope, expires_at, created_at, updated_at, is_valid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                    (new_id, user_id, provider, td.get("access_token", ""), td.get("refresh_token"), td.get("scope"), expires_at, now, now),
                )
                conn.commit()
            finally:
                conn.close()

            try:
                SPOTIFY_REFRESH.inc()
                GOOGLE_REFRESH_SUCCESS.labels(user_id).inc()
            except Exception:
                pass

            logger.info("google_refresh: success", extra={"user_id": user_id, "provider": provider})
            return
        except Exception as e:
            logger.exception("google_refresh: error", exc_info=e)
            try:
                SPOTIFY_REFRESH_ERROR.inc()
                GOOGLE_REFRESH_FAILED.labels(user_id, str(e)[:200]).inc()
            except Exception:
                pass
            delay = base_delay * (2 ** (attempt - 1))
            delay = delay + random.random()
            await asyncio.sleep(delay)

    logger.error("google_refresh: failed after attempts", extra={"user_id": user_id, "provider": provider})


async def run_once() -> None:
    now = int(time.time())
    candidates = _get_candidates(now)
    if not candidates:
        logger.info("google_refresh: no candidates")
        return

    tasks = []
    for user_id, provider, expires_at in candidates:
        tasks.append(_refresh_for_user(user_id, provider))

    await asyncio.gather(*tasks)


def main_loop() -> None:
    interval = int(os.getenv("GOOGLE_REFRESH_INTERVAL_SECONDS", "300"))
    loop = asyncio.get_event_loop()
    try:
        while True:
            loop.run_until_complete(run_once())
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("google_refresh: exiting")


if __name__ == "__main__":
    main_loop()


