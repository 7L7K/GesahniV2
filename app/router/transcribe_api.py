"""Compatibility wrappers for transcription endpoints.

These call into `app.api.transcribe` when available and otherwise provide the
lightweight queued response shape used by alias fallbacks.
"""
from __future__ import annotations

from typing import Any

from app.api import transcribe as _transcribe_api


async def transcribe_job(job_id: str) -> dict[str, Any]:
    try:
        # Start transcription if not already started
        res = await _transcribe_api.start_transcription(job_id)
        return res if isinstance(res, dict) else {"status": "accepted"}
    except Exception:
        return {"status": "accepted"}


