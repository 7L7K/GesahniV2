from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class QuietHours(BaseModel):
    start: str | None = None
    end: str | None = None

    model_config = ConfigDict(
        title="QuietHours",
        json_schema_extra={"example": {"start": "21:00", "end": "07:00"}},
    )


class TvConfig(BaseModel):
    enabled: bool = True
    theme: Literal["light", "dark"] = "dark"
    large_type: bool = True
    captioning: bool = True
    quiet_hours: QuietHours | None = None

    model_config = ConfigDict(
        title="TvConfig",
        json_schema_extra={
            "example": {
                "enabled": True,
                "theme": "dark",
                "large_type": True,
                "captioning": True,
                "quiet_hours": {"start": "21:00", "end": "07:00"},
            }
        },
    )


class TvConfigResponse(BaseModel):
    ok: bool = True
    config: TvConfig

    model_config = ConfigDict(
        title="TvConfigResponse",
        json_schema_extra={
            "example": {
                "ok": True,
                "config": {
                    "enabled": True,
                    "theme": "dark",
                    "large_type": True,
                    "captioning": True,
                    "quiet_hours": {"start": "21:00", "end": "07:00"},
                },
            }
        },
    )


__all__ = ["QuietHours", "TvConfig", "TvConfigResponse"]


