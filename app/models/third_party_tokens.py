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
    identity_id: Optional[str] = None
    # Provider-specific subject identifier (e.g., Google OIDC `sub`). Optional for non-OIDC providers.
    provider_sub: Optional[str] = None
    # OIDC issuer for the provider (e.g., https://accounts.google.com)
    provider_iss: Optional[str] = None
    # Encrypted access token blob (bytes) stored in DB
    access_token_enc: Optional[bytes] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    refresh_token: Optional[str] = None
    # Encrypted refresh token blob (bytes) stored in DB
    refresh_token_enc: Optional[bytes] = None
    # Envelope/key version for rotation
    envelope_key_version: int = 1
    last_refresh_at: int = 0
    refresh_error_count: int = 0
    scopes: Optional[str] = None
    # Optional JSON string to track per-service state
    service_state: Optional[str] = None
    # Audit of scopes union
    scope_union_since: int = 0
    scope_last_added_from: Optional[str] = None
    # Lineage: if replaced, which new row superseded this one
    replaced_by_id: Optional[str] = None
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
        # Expected column orders supported:
        # New canonical (with identity_id):
        # id, user_id, identity_id, provider, provider_sub, provider_iss, access_token, access_token_enc, refresh_token, refresh_token_enc,
        # Legacy (without identity_id):
        # id, user_id, provider, provider_sub, provider_iss, access_token, access_token_enc, refresh_token, refresh_token_enc,
        # envelope_key_version, last_refresh_at, refresh_error_count, scope, service_state, scope_union_since, scope_last_added_from, replaced_by_id,
        # expires_at, created_at, updated_at, is_valid
        id = row[0]
        user_id = row[1]
        idx = 2
        identity_id = None
        # Detect whether identity_id is present (new canonical schema)
        if len(row) >= 22:
            identity_id = row[2]
            provider = row[3]
            provider_sub = row[4] if len(row) > 4 else None
            provider_iss = row[5] if len(row) > 5 else None
            access_token = row[6]
            access_token_enc = row[7] if len(row) > 7 else None
            refresh_token = row[8] if len(row) > 8 else None
            refresh_token_enc = row[9] if len(row) > 9 else None
            envelope_key_version = int(row[10]) if len(row) > 10 and row[10] is not None else 1
            last_refresh_at = int(row[11]) if len(row) > 11 and row[11] is not None else 0
            refresh_error_count = int(row[12]) if len(row) > 12 and row[12] is not None else 0
            scope = row[13] if len(row) > 13 else None
            service_state = row[14] if len(row) > 14 else None
            scope_union_since = int(row[15]) if len(row) > 15 and row[15] is not None else 0
            scope_last_added_from = row[16] if len(row) > 16 else None
            replaced_by_id = row[17] if len(row) > 17 else None
            expires_at = row[18] if len(row) > 18 else 0
            created_at = row[19] if len(row) > 19 else 0
            updated_at = row[20] if len(row) > 20 else 0
            is_valid = bool(row[21]) if len(row) > 21 else True
        else:
            provider = row[2]
            provider_sub = row[3] if len(row) > 3 else None
            provider_iss = row[4] if len(row) > 4 else None
            access_token = row[5]
            access_token_enc = row[6] if len(row) > 6 else None
            refresh_token = row[7] if len(row) > 7 else None
            refresh_token_enc = row[8] if len(row) > 8 else None
            envelope_key_version = int(row[9]) if len(row) > 9 and row[9] is not None else 1
            last_refresh_at = int(row[10]) if len(row) > 10 and row[10] is not None else 0
            refresh_error_count = int(row[11]) if len(row) > 11 and row[11] is not None else 0
            scope = row[12] if len(row) > 12 else None
            service_state = row[13] if len(row) > 13 else None
            scope_union_since = int(row[14]) if len(row) > 14 and row[14] is not None else 0
            scope_last_added_from = row[15] if len(row) > 15 else None
            replaced_by_id = row[16] if len(row) > 16 else None
            expires_at = row[17] if len(row) > 17 else 0
            created_at = row[18] if len(row) > 18 else 0
            updated_at = row[19] if len(row) > 19 else 0
            is_valid = bool(row[20]) if len(row) > 20 else True

        return cls(
            id=id,
            user_id=user_id,
            identity_id=identity_id,
            provider=provider,
            provider_sub=provider_sub,
            access_token=access_token,
            access_token_enc=access_token_enc,
            refresh_token=refresh_token,
            refresh_token_enc=refresh_token_enc,
            envelope_key_version=envelope_key_version,
            last_refresh_at=last_refresh_at,
            refresh_error_count=refresh_error_count,
            scopes=scope,
            service_state=service_state,
            provider_iss=provider_iss,
            scope_union_since=scope_union_since,
            scope_last_added_from=scope_last_added_from,
            replaced_by_id=replaced_by_id,
            expires_at=expires_at,
            created_at=created_at,
            updated_at=updated_at,
            is_valid=is_valid,
        )

    def to_db_tuple(self) -> tuple:
        """Convert to tuple for database insertion/update."""
        return (
            self.id,
            self.user_id,
            self.identity_id,
            self.provider,
            self.provider_sub,
            self.provider_iss,
            self.access_token,
            self.access_token_enc,
            self.refresh_token,
            self.refresh_token_enc,
            self.envelope_key_version,
            self.last_refresh_at,
            self.refresh_error_count,
            self.scopes,
            self.service_state,
            self.scope_union_since,
            self.scope_last_added_from,
            self.replaced_by_id,
            self.expires_at,
            self.created_at,
            self.updated_at,
            1 if self.is_valid else 0,
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
    scopes: Optional[str] = None
    expires_at: Optional[int] = None
    is_valid: Optional[bool] = None

    def has_updates(self) -> bool:
        """Check if any fields have been set for update."""
        return any(
            value is not None for value in [
                self.access_token,
                self.refresh_token,
                self.scopes,
                self.expires_at,
                self.is_valid
            ]
        )
