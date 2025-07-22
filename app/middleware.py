import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .logging_config import req_id_var


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = str(uuid.uuid4())
        token = req_id_var.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        req_id_var.reset(token)
        return response
