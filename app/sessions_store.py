"""
PostgreSQL-based device sessions store.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

from sqlalchemy import select, update

from .db.core import get_async_db
from .db.models import AuthDevice
from .db.models import Session as SessionModel


class SessionsStore:
    def __init__(self, path: str | None = None) -> None:
        # Path parameter kept for compatibility but not used
        self._path = path

        # Session version cache: {sid: (version, timestamp)}
        self._version_cache: dict[str, tuple[int, float]] = {}
        self._cache_ttl_seconds = 60  # Cache session versions for 60 seconds

        # JTI blacklist cache: {jti: timestamp}
        self._jti_blacklist_cache: dict[str, float] = {}
        self._jti_cache_ttl_seconds = 300  # Cache JTI blacklist for 5 minutes

    async def create_session(
        self, user_id: str, *, did: str | None = None, device_name: str | None = None
    ) -> dict[str, str]:
        """Create a new logical login session for a device."""
        sid = str(uuid.uuid4())
        if not did:
            did = str(uuid.uuid4())

        async with get_async_db() as session:
            # Create or update device
            device_stmt = select(AuthDevice).where(AuthDevice.id == did)
            result = await session.execute(device_stmt)
            device = result.scalar_one_or_none()

            if not device:
                device = AuthDevice(
                    id=did,
                    user_id=user_id,
                    device_name=device_name or "Web",
                    ua_hash="",
                    ip_hash="",
                    created_at=datetime.now(UTC),
                    last_seen_at=datetime.now(UTC),
                )
                session.add(device)

            # Create session
            session_obj = SessionModel(
                id=sid,
                user_id=user_id,
                device_id=did,
                created_at=datetime.now(UTC),
                last_seen_at=datetime.now(UTC),
                mfa_passed=False,
                sess_ver=1,  # Initialize session version
            )
            session.add(session_obj)
            await session.commit()

        return {"sid": sid, "did": did}

    async def update_last_seen(self, sid: str) -> None:
        """Update last seen time for session."""
        async with get_async_db() as session:
            stmt = (
                update(SessionModel)
                .where(SessionModel.id == sid)
                .values(last_seen_at=datetime.now(UTC))
            )
            await session.execute(stmt)
            await session.commit()

    async def list_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """List all sessions for a user."""
        async with get_async_db() as session:
            stmt = (
                select(SessionModel, AuthDevice)
                .join(AuthDevice, SessionModel.device_id == AuthDevice.id)
                .where(SessionModel.user_id == user_id)
            )

            result = await session.execute(stmt)
            rows = result.all()

            sessions = []
            for session_obj, device in rows:
                sessions.append(
                    {
                        "sid": session_obj.id,
                        "did": device.id,
                        "device_name": device.device_name,
                        "created_at": (
                            session_obj.created_at.isoformat()
                            if session_obj.created_at
                            else None
                        ),
                        "last_seen": (
                            session_obj.last_seen_at.isoformat()
                            if session_obj.last_seen_at
                            else None
                        ),
                        "revoked": session_obj.revoked_at is not None,
                    }
                )

            return sessions

    async def revoke_family(self, sid: str) -> None:
        """Revoke a session family."""
        async with get_async_db() as session:
            # Get current session version and increment it
            select_stmt = select(SessionModel.sess_ver).where(SessionModel.id == sid)
            result = await session.execute(select_stmt)
            current_ver = result.scalar_one_or_none()

            if current_ver is not None:
                new_ver = current_ver + 1
            else:
                new_ver = 2  # Default to 2 if somehow sess_ver is missing

            stmt = (
                update(SessionModel)
                .where(SessionModel.id == sid)
                .values(
                    revoked_at=datetime.now(UTC),
                    sess_ver=new_ver
                )
            )
            await session.execute(stmt)
            await session.commit()

            # Update cache and invalidate for immediate effect
            self._set_cached_version(sid, new_ver)

    async def increment_session_version(self, sid: str) -> int | None:
        """Increment the session version to invalidate tokens.

        Returns the new session version, or None if session not found.
        """
        async with get_async_db() as session:
            # Get current session version
            select_stmt = select(SessionModel.sess_ver).where(SessionModel.id == sid)
            result = await session.execute(select_stmt)
            current_ver = result.scalar_one_or_none()

            if current_ver is None:
                return None

            # Increment version
            new_ver = current_ver + 1
            update_stmt = (
                update(SessionModel)
                .where(SessionModel.id == sid)
                .values(sess_ver=new_ver)
            )
            await session.execute(update_stmt)
            await session.commit()

            # Update cache with new version
            self._set_cached_version(sid, new_ver)

            return new_ver

    def _get_cached_version(self, sid: str) -> int | None:
        """Get session version from cache if valid."""
        if sid in self._version_cache:
            version, timestamp = self._version_cache[sid]
            if time.time() - timestamp < self._cache_ttl_seconds:
                return version
            else:
                # Cache expired, remove it
                del self._version_cache[sid]
        return None

    def _set_cached_version(self, sid: str, version: int) -> None:
        """Cache session version with timestamp."""
        self._version_cache[sid] = (version, time.time())

    def _invalidate_version_cache(self, sid: str) -> None:
        """Invalidate cached session version."""
        self._version_cache.pop(sid, None)

    async def get_session_version(self, sid: str) -> int | None:
        """Get the current session version with caching.

        Returns the session version, or None if session not found.
        """
        # Try cache first
        cached_version = self._get_cached_version(sid)
        if cached_version is not None:
            return cached_version

        # Cache miss, fetch from database
        async with get_async_db() as session:
            stmt = select(SessionModel.sess_ver).where(SessionModel.id == sid)
            result = await session.execute(stmt)
            version = result.scalar_one_or_none()

            # Cache the result if found
            if version is not None:
                self._set_cached_version(sid, version)

            return version

    async def validate_session_token(self, sid: str, token_version: int, jti: str) -> tuple[bool, str]:
        """Validate a JWT token against the session store.

        Args:
            sid: Session ID from JWT
            token_version: Session version from JWT
            jti: JWT ID from JWT

        Returns:
            Tuple of (is_valid, reason)
        """
        async with get_async_db() as session:
            # Get session info
            stmt = select(SessionModel).where(SessionModel.id == sid)
            result = await session.execute(stmt)
            session_obj = result.scalar_one_or_none()

            if not session_obj:
                return False, "session.not_found"

            # Check if session is revoked
            if session_obj.revoked_at is not None:
                return False, "session.revoked"

            # Check session version mismatch
            if session_obj.sess_ver != token_version:
                return False, "session.version_mismatch"

            # Check JTI blacklist (if implemented)
            if await self._is_jti_blacklisted(jti):
                return False, "token.blacklisted"

            return True, "valid"

    def _get_cached_jti_blacklist(self, jti: str) -> bool:
        """Check if JTI is in blacklist cache."""
        if jti in self._jti_blacklist_cache:
            timestamp = self._jti_blacklist_cache[jti]
            if time.time() - timestamp < self._jti_cache_ttl_seconds:
                return True
            else:
                # Cache expired, remove it
                del self._jti_blacklist_cache[jti]
        return False

    def _set_cached_jti_blacklist(self, jti: str) -> None:
        """Add JTI to blacklist cache."""
        self._jti_blacklist_cache[jti] = time.time()

    async def blacklist_jti(self, jti: str, ttl_seconds: int = 3600) -> None:
        """Add a JTI to the blacklist.

        Args:
            jti: JWT ID to blacklist
            ttl_seconds: How long to blacklist (default 1 hour)
        """
        # TODO: Implement persistent storage in Redis/database
        # For now, just use in-memory cache
        self._set_cached_jti_blacklist(jti)

        # Invalidate the cache entry after TTL
        import asyncio
        async def _cleanup():
            await asyncio.sleep(ttl_seconds)
            self._jti_blacklist_cache.pop(jti, None)

        # Run cleanup in background (fire and forget)
        asyncio.create_task(_cleanup())

    async def _is_jti_blacklisted(self, jti: str) -> bool:
        """Check if a JTI is blacklisted."""
        # Check cache first
        if self._get_cached_jti_blacklist(jti):
            return True

        # TODO: Check persistent storage (Redis/database)
        # For now, only cache is checked

        return False

    async def rename_device(self, user_id: str, did: str, new_name: str) -> bool:
        """Rename a device."""
        async with get_async_db() as session:
            # Verify device belongs to user
            stmt = select(AuthDevice).where(
                AuthDevice.id == did, AuthDevice.user_id == user_id
            )
            result = await session.execute(stmt)
            device = result.scalar_one_or_none()

            if not device:
                return False

            device.device_name = new_name
            await session.commit()

            return True

    async def revoke_device_sessions(self, user_id: str, did: str) -> None:
        """Revoke all sessions for a device."""
        async with get_async_db() as session:
            stmt = (
                update(SessionModel)
                .where(SessionModel.user_id == user_id, SessionModel.device_id == did)
                .values(revoked_at=datetime.now(UTC))
            )
            await session.execute(stmt)
            await session.commit()

    async def revoke_all_user_sessions(self, user_id: str) -> int:
        """Revoke all active sessions for a user.

        Returns the number of sessions revoked.
        """
        async with get_async_db() as session:
            # Get all session IDs for the user first (to update cache)
            select_stmt = select(SessionModel.id).where(SessionModel.user_id == user_id)
            result = await session.execute(select_stmt)
            session_ids = [row[0] for row in result.fetchall()]

            # Revoke all sessions and increment their versions
            stmt = (
                update(SessionModel)
                .where(SessionModel.user_id == user_id)
                .values(
                    revoked_at=datetime.now(UTC),
                    sess_ver=SessionModel.sess_ver + 1
                )
            )
            result = await session.execute(stmt)
            await session.commit()

            # Update cache for all affected sessions
            for sid in session_ids:
                # Invalidate cache - we'll get fresh version on next access
                self._invalidate_version_cache(sid)

            return len(session_ids)

    async def bump_session_version(self, sid: str | None | int) -> bool:
        """Increment session version for a specific session (idempotent).

        Returns True if successful, False if session not found or invalid.
        """
        # Handle invalid parameters
        if sid is None or not isinstance(sid, str) or not sid.strip():
            return False

        async with get_async_db() as session:
            try:
                stmt = (
                    update(SessionModel)
                    .where(SessionModel.id == sid)
                    .values(sess_ver=SessionModel.sess_ver + 1)
                )
                result = await session.execute(stmt)
                await session.commit()

                # Invalidate cache and get fresh version from database
                self._invalidate_version_cache(sid)
                new_version = await self.get_session_version(sid)
                if new_version is not None:
                    self._set_cached_version(sid, new_version)
                    return True

                return False
            except Exception as e:
                logger.warning(f"Failed to bump session version for {sid}: {e}")
                return False

    async def bump_all_user_sessions(self, user_id: str | None | int) -> int:
        """Increment session version for all user sessions (idempotent).

        Returns the number of sessions updated.
        """
        # Handle invalid parameters
        if user_id is None or not isinstance(user_id, str) or not user_id.strip():
            return 0

        try:
            return await self.revoke_all_user_sessions(user_id)
        except Exception as e:
            logger.warning(f"Failed to bump all user sessions for {user_id}: {e}")
            return 0


# Global instance
sessions_store = SessionsStore()
