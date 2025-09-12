"""User statistics models."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserStats(BaseModel):
    """User statistics model."""

    user_id: str
    login_count: int = Field(default=0, ge=0)
    last_login: str | None = None
    request_count: int = Field(default=0, ge=0)

    class Config:
        from_attributes = True


class UserStatsQuery(BaseModel):
    """Query parameters for user statistics."""

    user_id: str


class UserStatsUpdate(BaseModel):
    """Update parameters for user statistics."""

    login_count: int | None = Field(None, ge=0)
    last_login: str | None = None
    request_count: int | None = Field(None, ge=0)
