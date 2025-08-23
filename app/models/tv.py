from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class QuietHours(BaseModel):
    # Keep regex simple so invalid ranges (e.g. 25:00) are handled by route validators (400, not 422)
    start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")

    model_config = ConfigDict(
        title="QuietHours",
        json_schema_extra={"example": {"start": "22:00", "end": "06:00"}},
    )


class TvConfig(BaseModel):
    ambient_rotation: int = 30
    rail: Literal["safe", "admin", "open"] = "safe"
    quiet_hours: QuietHours | None = None
    default_vibe: str = "Calm Night"

    model_config = ConfigDict(
        title="TvConfig",
        json_schema_extra={
            "example": {
                "ambient_rotation": 45,
                "rail": "safe",
                "quiet_hours": {"start": "22:00", "end": "06:00"},
                "default_vibe": "Calm Night",
            }
        },
    )


class TvConfigResponse(BaseModel):
    status: str = "ok"
    config: TvConfig

    model_config = ConfigDict(
        title="TvConfigResponse",
        json_schema_extra={
            "example": {
                "status": "ok",
                "config": {
                    "ambient_rotation": 45,
                    "rail": "safe",
                    "quiet_hours": {"start": "22:00", "end": "06:00"},
                    "default_vibe": "Calm Night",
                },
            }
        },
    )


class TVConfigUpdate(BaseModel):
    ambient_rotation: int | None = None
    rail: str | None = (
        None  # allow any string; endpoints enforce allowed set for 400 not 422
    )
    quiet_hours: QuietHours | None = None
    default_vibe: str | None = None

    model_config = ConfigDict(
        title="TVConfigUpdate",
        json_schema_extra={
            "example": {
                "ambient_rotation": 15,
                "rail": "admin",
                "default_vibe": "Calm Night",
            }
        },
    )


__all__ = ["QuietHours", "TvConfig", "TvConfigResponse", "TVConfigUpdate"]
