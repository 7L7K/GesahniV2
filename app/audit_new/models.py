# app/audit/models.py
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Structured audit event model for append-only logging."""

    ts: datetime = Field(default_factory=datetime.utcnow)
    user_id: str | None = None
    route: str
    method: str
    status: int
    ip: str | None = None
    req_id: str | None = None
    scopes: list[str] = []
    action: str = "http_request"
    meta: dict[str, Any] = {}

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
