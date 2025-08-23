import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["Admin"])

def _is_dev():
    return os.getenv("ENV","dev").lower()=="dev" or os.getenv("DEV_MODE","0").lower() in {"1","true","yes","on"}

@router.get("/debug/config", include_in_schema=False)
async def debug_config():
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")
    import os

    from app.main import allow_credentials, origins
    return {
        "environment": {
            "CORS_ALLOW_ORIGINS": os.getenv("CORS_ALLOW_ORIGINS"),
            "APP_URL": os.getenv("APP_URL"),
            "API_URL": os.getenv("API_URL"),
            "HOST": os.getenv("HOST"),
            "PORT": os.getenv("PORT"),
            "CORS_ALLOW_CREDENTIALS": os.getenv("CORS_ALLOW_CREDENTIALS"),
        },
        "runtime": {
            "cors_origins": origins,
            "allow_credentials": allow_credentials,
            "server_host": os.getenv("HOST", "0.0.0.0"),
            "server_port": os.getenv("PORT", "8000"),
        },
        "frontend": {
            "expected_origin": "http://localhost:3000",
            "next_public_api_origin": os.getenv("NEXT_PUBLIC_API_ORIGIN"),
        }
    }

@router.get("/docs/ws", include_in_schema=False)
async def ws_helper_page():
    if not _is_dev():
        raise HTTPException(status_code=403, detail="forbidden")
    # Reuse your existing HTML page (shortened here)
    html = "<html><body><h1>WS Helper</h1></body></html>"
    return HTMLResponse(content=html, media_type="text/html")
