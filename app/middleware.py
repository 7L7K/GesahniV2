import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Set

from .logging_config import req_id_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = str(uuid.uuid4())
        token = req_id_var.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        req_id_var.reset(token)
        return response


class DedupMiddleware(BaseHTTPMiddleware):
    """Reject requests with a repeated ``X-Request-ID`` header."""

    def __init__(self, app):
        super().__init__(app)
        self._seen: Set[str] = set()

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID")
        if req_id and req_id in self._seen:
            return Response("Duplicate request", status_code=409)
        response = await call_next(request)
        if req_id:
            self._seen.add(req_id)
        return response
