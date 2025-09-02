"""
Root endpoint handler for the API.

Provides a friendly landing page for the root URL instead of an ugly 404.
"""

from fastapi import APIRouter
from starlette.responses import RedirectResponse, JSONResponse

router = APIRouter()


@router.get("/", include_in_schema=False)
def root():
    """Root endpoint - redirect to docs for a better user experience."""
    # Option: bounce to docs or health
    return RedirectResponse(url="/docs", status_code=303)


@router.get("/api", include_in_schema=False)
def api_info():
    """API info endpoint - provides links to available endpoints."""
    return JSONResponse({
        "ok": True,
        "message": "GesahniV2 API",
        "version": "2.0",
        "docs": "/docs",
        "health": "/v1/health",
        "endpoints": {
            "health": "/v1/health",
            "docs": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json"
        }
    })

