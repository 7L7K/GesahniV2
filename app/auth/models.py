"""Authentication models for GesahniV2."""

from typing import Any

from pydantic import BaseModel


class UserInfo(BaseModel):
    id: str | None = None
    email: str | None = None


class WhoAmIOut(BaseModel):
    is_authenticated: bool
    session_ready: bool
    user: UserInfo
    source: str
    version: int
    request_id: str | None = None
    schema_version: int | None = None
    generated_at: str | None = None
    user_id: str | None = None
    auth_source_conflict: bool | None = None


class LoginOut(BaseModel):
    status: str
    user_id: str
    access_token: str
    refresh_token: str
    session_id: str


class RegisterOut(BaseModel):
    access_token: str
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str


class TokenExamplesOut(BaseModel):
    samples: dict[str, Any]
    scopes: list[str]
    notes: list[str]


class RefreshOut(BaseModel):
    rotated: bool
    access_token: str | None = None
