from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from datetime import UTC, datetime

from sqlalchemy import select

from ..db.core import get_async_db
from ..db.models import ThirdPartyToken
from ..integrations.spotify.client import SpotifyAuthError
from ..metrics import SPOTIFY_REFRESH, SPOTIFY_REFRESH_ERROR

logger = logging.getLogger(__name__)

# Threshold in seconds before expiry to proactively refresh
REFRESH_AHEAD_SECONDS = int(os.getenv("SPOTIFY_REFRESH_AHEAD_SECONDS", "300"))


async def _get_candidates(now: int) -> list[tuple[str, str, int]]:
    """Return list of (user_id, provider, expires_at) for tokens expiring within window."""
    cutoff = datetime.fromtimestamp(now + REFRESH_AHEAD_SECONDS, tz=UTC)

    async with get_async_db() as session:
        # Query tokens that need refreshing
        stmt = (
            select(
                ThirdPartyToken.user_id,
                ThirdPartyToken.provider,
                ThirdPartyToken.expires_at,
            )
            .where(
                ThirdPartyToken.provider == "spotify",
                ThirdPartyToken.expires_at <= cutoff,
            )
            .order_by(ThirdPartyToken.expires_at.asc())
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        # Convert to expected format and deduplicate by (user_id, provider)
        seen = set()
        out = []
        for row in rows:
            user_id, provider, expires_at = row
            key = (user_id, provider)
            if key in seen:
                continue
            seen.add(key)
            # Convert expires_at to timestamp
            expires_ts = int(expires_at.timestamp()) if expires_at else 0
            out.append((user_id, provider, expires_ts))

        return out


async def _refresh_for_user(user_id: str, provider: str) -> None:
    """Refresh tokens for a user. Note: this now takes user_id directly instead of identity_id."""
    logger.info(
        "spotify_refresh: starting refresh",
        extra={"user_id": user_id, "provider": provider},
    )

    # Prefer centralized token refresh service which handles upsert/validation
    from ..auth_store_tokens import get_valid_token_with_auto_refresh

    attempt = 0
    max_attempts = 3
    base_delay = 1.0

    while attempt < max_attempts:
        attempt += 1
        try:
            logger.info(
                "spotify_refresh: attempting token exchange via refresh service",
                extra={"user_id": user_id, "provider": provider, "attempt": attempt},
            )
            # Force a refresh via the centralized service which will upsert refreshed tokens
            new_tokens = await get_valid_token_with_auto_refresh(
                user_id, provider, force_refresh=True
            )
            logger.info(
                "spotify_refresh: refresh returned tokens",
                extra={
                    "user_id": user_id,
                    "provider": provider,
                    "new_expires_at": getattr(new_tokens, "expires_at", None),
                },
            )

            # Mark metrics
            try:
                SPOTIFY_REFRESH.inc()
            except Exception:
                pass

            # Update updated_at timestamp for the token (the refresh service handles the actual token upsert)
            from app.util.ids import to_uuid
            
            now = datetime.now(UTC)
            async with get_async_db() as session:
                # Find the most recent token for this user/provider combination
                db_user_id = str(to_uuid(user_id))
                stmt = (
                    select(ThirdPartyToken)
                    .where(
                        ThirdPartyToken.user_id == db_user_id,
                        ThirdPartyToken.provider == provider,
                    )
                    .order_by(ThirdPartyToken.updated_at.desc())
                    .limit(1)
                )

                result = await session.execute(stmt)
                token = result.scalar_one_or_none()

                if token:
                    # Update the updated_at timestamp
                    token.updated_at = now
                    await session.commit()
                    logger.info(
                        "spotify_refresh: token updated successfully",
                        extra={
                            "user_id": user_id,
                            "provider": provider,
                            "updated_at": now,
                        },
                    )
                else:
                    logger.warning(
                        "spotify_refresh: no token found to update",
                        extra={"user_id": user_id, "provider": provider},
                    )

            logger.info(
                "spotify_refresh: exchange ok",
                extra={"user_id": user_id, "provider": provider},
            )
            return

        except SpotifyAuthError as e:
            logger.warning(
                "spotify_refresh: exchange failed",
                extra={
                    "user_id": user_id,
                    "provider": provider,
                    "error": str(e),
                    "attempt": attempt,
                },
            )

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
            logger.exception(
                "spotify_refresh: unexpected error",
                extra={"user_id": user_id, "provider": provider, "attempt": attempt},
                exc_info=e,
            )
            try:
                SPOTIFY_REFRESH_ERROR.inc()
            except Exception:
                pass
            delay = base_delay * (2 ** (attempt - 1))
            delay = delay + random.random()
            await asyncio.sleep(delay)

    logger.error(
        "spotify_refresh: failed after attempts",
        extra={"user_id": user_id, "provider": provider},
    )


async def run_once() -> None:
    now = int(time.time())
    candidates = await _get_candidates(now)
    if not candidates:
        logger.info("spotify_refresh: no candidates")
        return

    tasks = []
    for user_id, provider, _expires_at in candidates:
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
