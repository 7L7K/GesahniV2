"""
PostgreSQL-based music store for tokens and devices.
"""

from __future__ import annotations

import os
import time
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.core import get_async_db
from app.db.models import MusicDevice, MusicPreferences, MusicToken

MASTER_KEY = os.getenv("MUSIC_MASTER_KEY")


def _fernet() -> Fernet | None:
    if not MASTER_KEY:
        return None
    return Fernet(MASTER_KEY.encode())


async def _ensure_tables() -> None:
    """PostgreSQL schema is managed by migrations."""
    pass


async def get_music_token(user_id: str, provider: str) -> dict[str, Any] | None:
    """Get music token for user/provider."""
    async with get_async_db() as session:
        stmt = select(MusicToken).where(
            MusicToken.user_id == user_id, MusicToken.provider == provider
        )
        result = await session.execute(stmt)
        token = result.scalar_one_or_none()

        if not token:
            return None

        # Decrypt tokens
        access_token = None
        refresh_token = None

        fernet = _fernet()
        if fernet and token.access_token_enc:
            try:
                access_token = fernet.decrypt(token.access_token_enc).decode()
            except InvalidToken:
                pass

        if fernet and token.refresh_token_enc:
            try:
                refresh_token = fernet.decrypt(token.refresh_token_enc).decode()
            except InvalidToken:
                pass

        return {
            "user_id": token.user_id,
            "provider": token.provider,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "scope": (
                token.scope.decode() if isinstance(token.scope, bytes) else token.scope
            ),
            "expires_at": token.expires_at,
            "updated_at": token.updated_at,
        }


async def set_music_token(
    user_id: str,
    provider: str,
    access_token: str | None = None,
    refresh_token: str | None = None,
    scope: str | None = None,
    expires_at: int | None = None,
) -> None:
    """Set music token for user/provider."""
    async with get_async_db() as session:
        # Encrypt tokens
        access_token_enc = None
        refresh_token_enc = None

        fernet = _fernet()
        if fernet and access_token:
            access_token_enc = fernet.encrypt(access_token.encode())
        if fernet and refresh_token:
            refresh_token_enc = fernet.encrypt(refresh_token.encode())

        # Upsert token
        stmt = select(MusicToken).where(
            MusicToken.user_id == user_id, MusicToken.provider == provider
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            if access_token_enc is not None:
                existing.access_token_enc = access_token_enc
            if refresh_token_enc is not None:
                existing.refresh_token_enc = refresh_token_enc
            if scope is not None:
                existing.scope = scope
            if expires_at is not None:
                existing.expires_at = expires_at
            existing.updated_at = int(time.time())
        else:
            token = MusicToken(
                user_id=user_id,
                provider=provider,
                access_token_enc=access_token_enc,
                refresh_token_enc=refresh_token_enc,
                scope=scope,
                expires_at=expires_at,
                updated_at=int(time.time()),
            )
            session.add(token)

        await session.commit()


async def get_music_devices(provider: str) -> list[dict[str, Any]]:
    """Get all devices for a provider."""
    async with get_async_db() as session:
        stmt = select(MusicDevice).where(MusicDevice.provider == provider)
        result = await session.execute(stmt)
        devices = result.scalars().all()

        return [
            {
                "provider": device.provider,
                "device_id": device.device_id,
                "room": device.room,
                "name": device.name,
                "last_seen": device.last_seen,
                "capabilities": device.capabilities,
            }
            for device in devices
        ]


async def set_music_device(
    provider: str,
    device_id: str,
    room: str | None = None,
    name: str | None = None,
    capabilities: str | None = None,
) -> None:
    """Set music device info."""
    async with get_async_db() as session:
        stmt = select(MusicDevice).where(
            MusicDevice.provider == provider, MusicDevice.device_id == device_id
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        now = int(time.time())

        if existing:
            if room is not None:
                existing.room = room
            if name is not None:
                existing.name = name
            if capabilities is not None:
                existing.capabilities = capabilities
            existing.last_seen = now
        else:
            device = MusicDevice(
                provider=provider,
                device_id=device_id,
                room=room,
                name=name,
                last_seen=now,
                capabilities=capabilities,
            )
            session.add(device)

        await session.commit()


async def update_device_last_seen(provider: str, device_id: str) -> None:
    """Update device last seen time."""
    async with get_async_db() as session:
        stmt = (
            update(MusicDevice)
            .where(MusicDevice.provider == provider, MusicDevice.device_id == device_id)
            .values(last_seen=int(time.time()))
        )
        await session.execute(stmt)
        await session.commit()


async def get_music_preferences(user_id: str) -> dict[str, Any] | None:
    """Get music preferences for user."""
    async with get_async_db() as session:
        stmt = select(MusicPreferences).where(MusicPreferences.user_id == user_id)
        result = await session.execute(stmt)
        prefs = result.scalar_one_or_none()

        if not prefs:
            return None

        return {
            "user_id": prefs.user_id,
            "default_provider": prefs.default_provider,
            "quiet_start": prefs.quiet_start,
            "quiet_end": prefs.quiet_end,
            "quiet_max_volume": prefs.quiet_max_volume,
            "allow_explicit": prefs.allow_explicit,
        }


async def set_music_preferences(
    user_id: str,
    default_provider: str | None = None,
    quiet_start: str | None = None,
    quiet_end: str | None = None,
    quiet_max_volume: int | None = None,
    allow_explicit: bool | None = None,
) -> None:
    """Set music preferences for user."""
    async with get_async_db() as session:
        stmt = select(MusicPreferences).where(MusicPreferences.user_id == user_id)
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            if default_provider is not None:
                existing.default_provider = default_provider
            if quiet_start is not None:
                existing.quiet_start = quiet_start
            if quiet_end is not None:
                existing.quiet_end = quiet_end
            if quiet_max_volume is not None:
                existing.quiet_max_volume = quiet_max_volume
            if allow_explicit is not None:
                existing.allow_explicit = allow_explicit
        else:
            prefs = MusicPreferences(
                user_id=user_id,
                default_provider=default_provider or "spotify",
                quiet_start=quiet_start or "22:00",
                quiet_end=quiet_end or "07:00",
                quiet_max_volume=quiet_max_volume or 30,
                allow_explicit=allow_explicit if allow_explicit is not None else True,
            )
            session.add(prefs)

        await session.commit()


# Idempotency functions for caching responses
async def get_idempotent(
    key: str, user_id: str, session: AsyncSession | None = None
) -> dict | None:
    """Get cached idempotent response from database."""
    from app.db.core import get_async_db

    if session is None:
        async for s in get_async_db():
            return await _get_idempotent_impl(key, user_id, s)
    else:
        return await _get_idempotent_impl(key, user_id, session)

    return None


async def _get_idempotent_impl(
    key: str, user_id: str, session: AsyncSession
) -> dict | None:
    """Internal implementation for getting idempotent response."""
    # This would need a database table for music_idempotency
    # For now, return None to disable caching until table is created
    return None


async def set_idempotent(
    key: str, user_id: str, response: dict, session: AsyncSession | None = None
) -> None:
    """Store idempotent response in database."""
    from app.db.core import get_async_db

    if session is None:
        async for s in get_async_db():
            await _set_idempotent_impl(key, user_id, response, s)
            break
    else:
        await _set_idempotent_impl(key, user_id, response, session)


async def _set_idempotent_impl(
    key: str, user_id: str, response: dict, session: AsyncSession
) -> None:
    """Internal implementation for storing idempotent response."""
    # This would need a database table for music_idempotency
    # For now, do nothing until table is created
    pass
