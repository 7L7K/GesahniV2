from __future__ import annotations

import asyncio
import logging
import os
import random
import sqlite3
import time
from typing import List, Tuple

from ..integrations.spotify.client import SpotifyClient, SpotifyAuthError
from ..auth_store import get_user_id_by_identity_id
from ..metrics import SPOTIFY_REFRESH, SPOTIFY_REFRESH_ERROR

logger = logging.getLogger(__name__)

# Threshold in seconds before expiry to proactively refresh
REFRESH_AHEAD_SECONDS = int(os.getenv("SPOTIFY_REFRESH_AHEAD_SECONDS", "300"))

# Path to tokens DB: prefer env override, otherwise use TokenDAO module default
from ..auth_store_tokens import TokenDAO, _default_db_path


def _resolve_db_path() -> str:
    """Resolve the tokens DB path at runtime (env overrides class default)."""
    return os.getenv("THIRD_PARTY_TOKENS_DB") or _default_db_path()


def _get_candidates(now: int) -> List[Tuple[str, str, int]]:
    """Return list of (user_id, provider, expires_at) for tokens expiring within window."""
    out = []
    conn = sqlite3.connect(_resolve_db_path())
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        cur = conn.cursor()
        cutoff = now + REFRESH_AHEAD_SECONDS
        # Select latest valid token per user/provider that expires before cutoff
        # Use identity_id as canonical grouping key
        cur.execute(
            """
            SELECT identity_id, provider, expires_at
            FROM third_party_tokens
            WHERE is_valid = 1 AND expires_at <= ? AND identity_id IS NOT NULL
            GROUP BY identity_id, provider
            """,
            (cutoff,),
        )
        rows = cur.fetchall()
        for r in rows:
            out.append((r[0], r[1], int(r[2] or 0)))
    finally:
        conn.close()
    return out


async def _refresh_for_user(identity_id: str, provider: str) -> None:
    # Get user_id from identity_id
    user_id = await get_user_id_by_identity_id(identity_id)
    if not user_id:
        logger.error("spotify_refresh: no user_id found for identity_id", extra={"identity_id": identity_id, "provider": provider})
        return

    logger.info("spotify_refresh: starting refresh", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider})

    client = SpotifyClient(user_id)
    attempt = 0
    max_attempts = 3
    base_delay = 1.0

    while attempt < max_attempts:
        attempt += 1
        try:
            logger.info("spotify_refresh: attempting token exchange", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider, "attempt": attempt})
            await client._refresh_tokens()

            # Mark metrics
            try:
                SPOTIFY_REFRESH.inc()
            except Exception:
                pass

            # Update last_refresh_at and reset error count for latest token row by identity
            now = int(time.time())
            conn = sqlite3.connect(_resolve_db_path())
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id FROM third_party_tokens WHERE identity_id = ? AND provider = ? AND is_valid = 1 ORDER BY created_at DESC LIMIT 1",
                    (identity_id, provider),
                )
                row = cur.fetchone()
                if row:
                    token_id = row[0]
                    cur.execute(
                        "UPDATE third_party_tokens SET last_refresh_at = ?, refresh_error_count = 0 WHERE id = ?",
                        (now, token_id),
                    )
                    conn.commit()
                    logger.info("spotify_refresh: token updated successfully", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider, "token_id": token_id, "new_expires_at": "updated"})
            finally:
                conn.close()

            logger.info("spotify_refresh: exchange ok", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider})
            return
        except SpotifyAuthError as e:
            logger.warning("spotify_refresh: exchange failed", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider, "error": str(e), "attempt": attempt})
            # increment error counter on DB
            conn = sqlite3.connect(_resolve_db_path())
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT id, refresh_error_count FROM third_party_tokens WHERE identity_id = ? AND provider = ? AND is_valid = 1 ORDER BY created_at DESC LIMIT 1",
                    (identity_id, provider),
                )
                r = cur.fetchone()
                if r:
                    token_id = r[0]
                    err_count = int(r[1] or 0) + 1
                    cur.execute(
                        "UPDATE third_party_tokens SET refresh_error_count = ? WHERE id = ?",
                        (err_count, token_id),
                    )
                    conn.commit()
            finally:
                conn.close()
            try:
                SPOTIFY_REFRESH_ERROR.inc()
            except Exception:
                pass
            # Backoff with jitter
            delay = base_delay * (2 ** (attempt - 1))
            delay = delay + random.random()
            await asyncio.sleep(delay)
            continue
        except Exception as e:
            logger.exception("spotify_refresh: unexpected error", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider, "attempt": attempt}, exc_info=e)
            try:
                SPOTIFY_REFRESH_ERROR.inc()
            except Exception:
                pass
            delay = base_delay * (2 ** (attempt - 1))
            delay = delay + random.random()
            await asyncio.sleep(delay)

    logger.error("spotify_refresh: failed after attempts", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider})


async def run_once() -> None:
    now = int(time.time())
    candidates = _get_candidates(now)
    if not candidates:
        logger.info("spotify_refresh: no candidates")
        return

    tasks = []
    for user_id, provider, expires_at in candidates:
        tasks.append(_refresh_for_user(user_id, provider))

    await asyncio.gather(*tasks)


def main_loop() -> None:
    """Run refresh loop every 5 minutes. Can be scheduled instead by calling run_once."""
    interval = int(os.getenv("SPOTIFY_REFRESH_INTERVAL_SECONDS", "300"))
    loop = asyncio.get_event_loop()
    try:
        while True:
            loop.run_until_complete(run_once())
            time.sleep(interval)
    except KeyboardInterrupt:
        logger.info("spotify_refresh: exiting")


if __name__ == "__main__":
    main_loop()

