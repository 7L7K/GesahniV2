from __future__ import annotations

import asyncio
import logging
import os
import random
import secrets
import time
from datetime import UTC, datetime

from sqlalchemy import select

from ..db.core import get_async_db
from ..db.models import ThirdPartyToken
from ..integrations.google.oauth import refresh_token
from ..metrics import (
    GOOGLE_REFRESH_FAILED,
    GOOGLE_REFRESH_SUCCESS,
    SPOTIFY_REFRESH,
    SPOTIFY_REFRESH_ERROR,
)

logger = logging.getLogger(__name__)

# Threshold in seconds before expiry to proactively refresh
REFRESH_AHEAD_SECONDS = int(os.getenv("GOOGLE_REFRESH_AHEAD_SECONDS", "300"))


async def _get_candidates(now: int) -> list[tuple[str, str, int]]:
    """Return list of (user_id, provider, expires_at) for Google tokens expiring within window."""
    cutoff = datetime.fromtimestamp(now + REFRESH_AHEAD_SECONDS, tz=UTC)

    async with get_async_db() as session:
        # Query Google tokens that need refreshing
        stmt = (
            select(
                ThirdPartyToken.user_id,
                ThirdPartyToken.provider,
                ThirdPartyToken.expires_at,
            )
            .where(
                ThirdPartyToken.provider == "google",
                ThirdPartyToken.expires_at <= cutoff,
            )
            .group_by(ThirdPartyToken.user_id, ThirdPartyToken.provider)
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        # Convert to expected format
        out = []
        for row in rows:
            user_id, provider, expires_at = row
            # Convert expires_at to timestamp
            expires_ts = int(expires_at.timestamp()) if expires_at else 0
            out.append((user_id, provider, expires_ts))

        return out


async def _refresh_for_user(user_id: str, provider: str) -> None:
    """Refresh Google tokens for a user. Note: this now takes user_id directly."""
    attempt = 0
    max_attempts = 3
    base_delay = 1.0

    while attempt < max_attempts:
        attempt += 1
        try:
            # Fetch latest token row by user_id
            async with get_async_db() as session:
                stmt = (
                    select(ThirdPartyToken)
                    .where(
                        ThirdPartyToken.user_id == user_id,
                        ThirdPartyToken.provider == provider,
                    )
                    .order_by(ThirdPartyToken.updated_at.desc())
                    .limit(1)
                )

                result = await session.execute(stmt)
                token = result.scalar_one_or_none()

                if not token or not token.refresh_token:
                    logger.warning(
                        "google_refresh: no refresh token found",
                        extra={"user_id": user_id, "provider": provider},
                    )
                    return

                refresh_tok = (
                    token.refresh_token.decode()
                    if isinstance(token.refresh_token, bytes)
                    else token.refresh_token
                )

            td = await refresh_token(refresh_tok)

            # Persist new token row using the centralized upsert service
            from ..auth_store_tokens import upsert_token

            now = int(time.time())
            expires_at = int(
                td.get("expires_at", now + int(td.get("expires_in", 3600)))
            )

            # Create new token object for upsert
            from ..models.third_party_tokens import ThirdPartyToken

            new_token = ThirdPartyToken(
                id=f"google:{secrets.token_hex(8)}",
                user_id=user_id,
                identity_id="",  # Not used for Google tokens
                provider="google",
                access_token=td.get("access_token", "").encode(),
                refresh_token=(
                    td.get("refresh_token", "").encode()
                    if td.get("refresh_token")
                    else None
                ),
                scopes=td.get("scope"),
                expires_at=expires_at,
                created_at=now,
                updated_at=now,
            )
            await upsert_token(new_token)

            try:
                SPOTIFY_REFRESH.inc()
                GOOGLE_REFRESH_SUCCESS.labels(user_id).inc()
            except Exception:
                pass

            logger.info(
                "google_refresh: success",
                extra={"user_id": user_id, "provider": provider},
            )
            return

        except Exception as e:
            logger.exception(
                "google_refresh: error",
                extra={"user_id": user_id, "provider": provider},
                exc_info=e,
            )
            try:
                SPOTIFY_REFRESH_ERROR.inc()
                GOOGLE_REFRESH_FAILED.labels(user_id, str(e)[:200]).inc()
            except Exception:
                pass
            delay = base_delay * (2 ** (attempt - 1))
            delay = delay + random.random()
            await asyncio.sleep(delay)

    logger.error(
        "google_refresh: failed after attempts",
        extra={"user_id": user_id, "provider": provider},
    )


async def run_once() -> None:
    now = int(time.time())
    candidates = await _get_candidates(now)
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
