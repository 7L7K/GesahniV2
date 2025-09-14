"""Chat message persistence repository."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ChatMessage


async def save_messages(
    session: AsyncSession,
    user_id: str,
    rid: str,
    messages: list[dict[str, str]],
) -> None:
    """Save chat messages for a request.

    Args:
        session: Database session
        user_id: User ID
        rid: Request ID
        messages: List of message dicts with 'role' and 'content' keys
    """
    if not messages:
        return

    # Create ChatMessage objects
    chat_messages = [
        ChatMessage(
            user_id=user_id,
            rid=rid,
            role=msg["role"],
            content=msg["content"],
        )
        for msg in messages
        if "role" in msg and "content" in msg
    ]

    if chat_messages:
        session.add_all(chat_messages)
        await session.commit()


async def get_messages_by_rid(
    session: AsyncSession,
    user_id: str,
    rid: str,
) -> Sequence[ChatMessage]:
    """Get chat messages for a specific request ID.

    Args:
        session: Database session
        user_id: User ID (for security)
        rid: Request ID

    Returns:
        List of ChatMessage objects ordered by creation time
    """
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id, ChatMessage.rid == rid)
        .order_by(ChatMessage.created_at)
    )

    result = await session.execute(stmt)
    return result.scalars().all()


async def get_recent_messages(
    session: AsyncSession,
    user_id: str,
    limit: int = 50,
) -> Sequence[ChatMessage]:
    """Get recent chat messages for a user.

    Args:
        session: Database session
        user_id: User ID
        limit: Maximum number of messages to return

    Returns:
        List of recent ChatMessage objects ordered by creation time (newest first)
    """
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )

    result = await session.execute(stmt)
    return result.scalars().all()


async def delete_old_messages(
    session: AsyncSession,
    user_id: str,
    days_old: int = 30,
) -> int:
    """Delete old chat messages for cleanup.

    Args:
        session: Database session
        user_id: User ID
        days_old: Delete messages older than this many days

    Returns:
        Number of messages deleted
    """
    dt.datetime.now(dt.UTC) - dt.timedelta(days=days_old)

    # For now, just return 0 as we don't want to implement deletion in the initial version
    # This can be implemented later if needed
    return 0
