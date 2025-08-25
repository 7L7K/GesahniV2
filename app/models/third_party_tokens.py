from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ThirdPartyToken:
    """Represents a third-party OAuth token stored in the database."""

    user_id: str
    provider: str  # 'spotify', 'google', 'apple', etc.
    access_token: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    expires_at: int = 0  # epoch seconds
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    is_valid: bool = True

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """Check if token is expired (with optional buffer time)."""
        return (self.expires_at - buffer_seconds) <= time.time()

    def time_until_expiry(self) -> int:
        """Get seconds until token expires (negative if already expired)."""
        return int(self.expires_at - time.time())

    def mark_updated(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = int(time.time())

    @classmethod
    def from_db_row(cls, row: tuple) -> ThirdPartyToken:
        """Create instance from database row tuple."""
        return cls(
            id=row[0],
            user_id=row[1],
            provider=row[2],
            access_token=row[3],
            refresh_token=row[4],
            scope=row[5],
            expires_at=row[6],
            created_at=row[7],
            updated_at=row[8],
            is_valid=bool(row[9]) if len(row) > 9 else True
        )

    def to_db_tuple(self) -> tuple:
        """Convert to tuple for database insertion/update."""
        return (
            self.id,
            self.user_id,
            self.provider,
            self.access_token,
            self.refresh_token,
            self.scope,
            self.expires_at,
            self.created_at,
            self.updated_at,
            1 if self.is_valid else 0
        )

    def __post_init__(self) -> None:
        """Validate required fields after initialization."""
        if not self.user_id or not self.provider or not self.access_token:
            raise ValueError("user_id, provider, and access_token are required")

        if self.expires_at <= 0:
            raise ValueError("expires_at must be a positive timestamp")


@dataclass
class TokenQuery:
    """Query parameters for token lookups."""
    user_id: str
    provider: str

    def __post_init__(self) -> None:
        if not self.user_id or not self.provider:
            raise ValueError("user_id and provider are required")


@dataclass
class TokenUpdate:
    """Fields that can be updated on a token."""
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    expires_at: Optional[int] = None
    is_valid: Optional[bool] = None

    def has_updates(self) -> bool:
        """Check if any fields have been set for update."""
        return any(
            value is not None for value in [
                self.access_token,
                self.refresh_token,
                self.scope,
                self.expires_at,
                self.is_valid
            ]
        )
