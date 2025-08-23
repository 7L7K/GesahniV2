from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class OkResponse(BaseModel):
    ok: bool = True
    status: str = "ok"

    # Force stable OpenAPI component name and include example
    model_config = ConfigDict(
        title="OkResponse",
        json_schema_extra={"example": {"ok": True, "status": "ok"}},
    )
