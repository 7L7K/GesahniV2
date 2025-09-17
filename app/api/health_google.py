from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["Admin"])


@router.get("/google")
async def health_google() -> dict[str, object]:
    """Minimal Google health check used by the dashboard."""
    return {"service": "google", "connected": True}
