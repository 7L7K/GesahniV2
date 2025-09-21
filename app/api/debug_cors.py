# app/api/debug_cors.py
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/cors-info")
async def cors_info(request: Request):
    # What FastAPI/Starlette sees from this request
    return JSONResponse({
        "origin_header": request.headers.get("origin"),
        "access_control_request_method": request.headers.get("access-control-request-method"),
        "access_control_request_headers": request.headers.get("access-control-request-headers"),
        "method": request.method,
    })
