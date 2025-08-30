from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/v1/_schema/error-envelope.json", include_in_schema=False)
async def error_envelope_schema():
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://gesahni.local/schema/error-envelope.json",
        "title": "ErrorEnvelope",
        "type": "object",
        "required": ["code", "message"],
        "properties": {
            "code": {"type": "string"},
            "message": {"type": "string"},
            "hint": {"type": ["string", "null"]},
            "details": {
                "type": "object",
                "additionalProperties": True,
                "properties": {
                    "req_id": {"type": "string"},
                    "trace_id": {"type": ["string", "null"]},
                    "timestamp": {"type": "string"},
                    "error_id": {"type": "string"},
                    "status_code": {"type": ["integer", "null"]},
                    "path": {"type": ["string", "null"]},
                    "method": {"type": ["string", "null"]},
                },
            },
        },
        "additionalProperties": False,
    }
    return JSONResponse(schema)

