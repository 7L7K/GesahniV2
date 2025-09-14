"""
PostgreSQL-based device sessions store.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update

from .db.core import get_async_db
from .db.models import AuthDevice
from .db.models import Session as SessionModel


class SessionsStore:
    def __init__(self, path: str | None = None) -> None:
        # Path parameter kept for compatibility but not used
        self._path = path

    async def create_session(
        self, user_id: str, *, did: str | None = None, device_name: str | None = None
    ) -> dict[str, str]:
        """Create a new logical login session for a device."""
        sid = uuid.uuid4().hex
        if not did:
            did = uuid.uuid4().hex

        session_gen = get_async_db()
        session = await anext(session_gen)
        try:
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
            )
            session.add(session_obj)
            await session.commit()
        finally:
            await session.close()

        return {"sid": sid, "did": did}

    async def update_last_seen(self, sid: str) -> None:
        """Update last seen time for session."""
        session_gen = get_async_db()
        session = await anext(session_gen)
        try:
            stmt = (
                update(SessionModel)
                .where(SessionModel.id == sid)
                .values(last_seen_at=datetime.now(UTC))
            )
            await session.execute(stmt)
            await session.commit()
        finally:
            await session.close()

    async def list_user_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """List all sessions for a user."""
        session_gen = get_async_db()
        session = await anext(session_gen)
        try:
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

            result_sessions = sessions
        finally:
            await session.close()

        return result_sessions

    async def revoke_family(self, sid: str) -> None:
        """Revoke a session family."""
        session_gen = get_async_db()
        session = await anext(session_gen)
        try:
            stmt = (
                update(SessionModel)
                .where(SessionModel.id == sid)
                .values(revoked_at=datetime.now(UTC))
            )
            await session.execute(stmt)
            await session.commit()
        finally:
            await session.close()

    async def rename_device(self, user_id: str, did: str, new_name: str) -> bool:
        """Rename a device."""
        session_gen = get_async_db()
        session = await anext(session_gen)
        try:
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

            result_success = True
        finally:
            await session.close()

        return result_success

    async def revoke_device_sessions(self, user_id: str, did: str) -> None:
        """Revoke all sessions for a device."""
        session_gen = get_async_db()
        session = await anext(session_gen)
        try:
            stmt = (
                update(SessionModel)
                .where(SessionModel.user_id == user_id, SessionModel.device_id == did)
                .values(revoked_at=datetime.now(UTC))
            )
            await session.execute(stmt)
            await session.commit()
        finally:
            await session.close()


# Global instance
sessions_store = SessionsStore()
