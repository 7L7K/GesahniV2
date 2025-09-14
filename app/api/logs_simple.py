from fastapi import APIRouter, Depends, Query

from ..deps.user import get_current_user_id
from ..logging_config import get_last_errors

router = APIRouter(tags=["Admin"])


@router.get("/logs")
async def logs(
    limit: int = Query(default=100, ge=1, le=500),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return recent error logs for the authenticated user.

    Uses an in-process ring buffer populated by the logging configuration.
    """
    items = get_last_errors(limit)
    return {"logs": items}
