from __future__ import annotations

import asyncio
import logging
import os
import random
import sqlite3
import time

from ..auth_store import get_user_id_by_identity_id
from ..integrations.spotify.client import SpotifyAuthError
from ..metrics import SPOTIFY_REFRESH, SPOTIFY_REFRESH_ERROR

logger = logging.getLogger(__name__)

# Threshold in seconds before expiry to proactively refresh
REFRESH_AHEAD_SECONDS = int(os.getenv("SPOTIFY_REFRESH_AHEAD_SECONDS", "300"))

# Path to tokens DB: prefer env override, otherwise use TokenDAO module default
from ..auth_store_tokens import TokenDAO


def _resolve_db_path() -> str:
    """Resolve the tokens DB path at runtime. Prefer explicit env var, otherwise
    use the TokenDAO's configured db_path so tests that override module defaults
    are respected.
    """
    # If explicit env override provided, honor it
    env_path = os.getenv("THIRD_PARTY_TOKENS_DB")
    if env_path:
        return env_path
    # Otherwise prefer module-level DEFAULT_DB_PATH if set (tests may override it)
    try:
        import app.auth_store_tokens as ast

        if getattr(ast, "DEFAULT_DB_PATH", None):
            return str(ast.DEFAULT_DB_PATH)
    except Exception:
        pass
    # Fallback to creating a DAO and using its db_path or the default resolver
    try:
        dao = TokenDAO()
        return dao.db_path
    except Exception:
        from .auth_store_tokens import _default_db_path

        return _default_db_path()


def _get_candidates(now: int) -> list[tuple[str, str, int]]:
    """Return list of (user_id, provider, expires_at) for tokens expiring within window."""
    out = []
    # Resolve DB path with priority: explicit env var > module DEFAULT_DB_PATH > TokenDAO default
    db_path = None
    env_path = os.getenv("THIRD_PARTY_TOKENS_DB")
    if env_path:
        db_path = env_path
    else:
        try:
            import app.auth_store_tokens as ast

            if getattr(ast, "DEFAULT_DB_PATH", None):
                db_path = str(ast.DEFAULT_DB_PATH)
        except Exception:
            db_path = None
    if not db_path:
        try:
            dao = TokenDAO()
            db_path = dao.db_path
        except Exception:
            db_path = _resolve_db_path()

    # Try multiple candidate DB paths to be resilient in test environments
    candidate_paths = []
    # explicit env
    env_path = os.getenv("THIRD_PARTY_TOKENS_DB")
    if env_path:
        candidate_paths.append(env_path)
    # module-level default if present
    try:
        import app.auth_store_tokens as ast

        # module-level DEFAULT_DB_PATH
        if getattr(ast, "DEFAULT_DB_PATH", None):
            candidate_paths.append(str(ast.DEFAULT_DB_PATH))
        # class-level TokenDAO.DEFAULT_DB_PATH (tests set this in some fixtures)
        try:
            td = getattr(ast, "TokenDAO", None)
            if td is not None and getattr(td, "DEFAULT_DB_PATH", None):
                candidate_paths.append(str(td.DEFAULT_DB_PATH))
        except Exception:
            pass
    except Exception:
        pass
    # TokenDAO default
    try:
        candidate_paths.append(TokenDAO().db_path)
    except Exception:
        pass
    # fallback to repo default file
    candidate_paths.append("third_party_tokens.db")

    cutoff = now + REFRESH_AHEAD_SECONDS
    seen = set()
    for p in candidate_paths:
        try:
            if not p or not os.path.exists(p):
                continue
            conn = sqlite3.connect(p)
            conn.execute("PRAGMA foreign_keys=ON")
            cur = conn.cursor()
            cur.execute(
                """
                SELECT identity_id, provider, expires_at
                FROM third_party_tokens
                WHERE is_valid = 1 AND expires_at <= ? AND identity_id IS NOT NULL
                ORDER BY expires_at ASC
                """,
                (cutoff,),
            )
            rows = cur.fetchall()
            for r in rows:
                key = (r[0], r[1])
                if key in seen:
                    continue
                seen.add(key)
                out.append((r[0], r[1], int(r[2] or 0)))
        except Exception:
            # ignore DB-specific errors and try next path
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass
    return out


async def _refresh_for_user(identity_id: str, provider: str) -> None:
    # Get user_id from identity_id
    user_id = await get_user_id_by_identity_id(identity_id)
    if not user_id:
        logger.error("spotify_refresh: no user_id found for identity_id", extra={"identity_id": identity_id, "provider": provider})
        return

    logger.info("spotify_refresh: starting refresh", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider})

    # Prefer centralized token refresh service which handles upsert/validation
    from ..auth_store_tokens import get_valid_token_with_auto_refresh

    attempt = 0
    max_attempts = 3
    base_delay = 1.0

    while attempt < max_attempts:
        attempt += 1
        try:
            logger.info("spotify_refresh: attempting token exchange via refresh service", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider, "attempt": attempt})
            # Force a refresh via the centralized service which will upsert refreshed tokens
            new_tokens = await get_valid_token_with_auto_refresh(user_id, provider, force_refresh=True)
            logger.info("spotify_refresh: refresh returned tokens", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider, "new_expires_at": getattr(new_tokens, 'expires_at', None)})

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
                    # read current expires_at for debug
                    try:
                        cur.execute("SELECT expires_at FROM third_party_tokens WHERE id = ?", (token_id,))
                        cur_row = cur.fetchone()
                        curr_expires = int(cur_row[0]) if cur_row and cur_row[0] is not None else None
                    except Exception:
                        curr_expires = None

                    logger.info("spotify_refresh: updating token", extra={"token_id": token_id, "current_expires_at": curr_expires, "new_expires_at": getattr(new_tokens, 'expires_at', None)})

                    cur.execute(
                        "UPDATE third_party_tokens SET last_refresh_at = ?, refresh_error_count = 0 WHERE id = ?",
                        (now, token_id),
                    )
                    # Also update expires_at if refresh returned new token expiry
                    try:
                        if new_tokens and getattr(new_tokens, 'expires_at', None):
                            cur.execute("UPDATE third_party_tokens SET expires_at = ? WHERE id = ?", (int(new_tokens.expires_at), token_id))
                    except Exception:
                        pass
                    conn.commit()
                    logger.info("spotify_refresh: token updated successfully", extra={"identity_id": identity_id, "user_id": user_id, "provider": provider, "token_id": token_id, "updated_expires_at": getattr(new_tokens, 'expires_at', 'updated')})
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

