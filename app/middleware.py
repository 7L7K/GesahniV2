import uuid
import asyncio
import time
from hashlib import sha256
from typing import Set

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .logging_config import req_id_var
from .telemetry import LogRecord, log_record_var, utc_now
from .history import append_history
from .analytics import record_latency, latency_p95
from .user_store import user_store
from .env_utils import load_env
from . import metrics


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


def _anon_user_id(source: Request | str | None) -> str:
    """Return a stable anonymous identifier.

    Accepts either a FastAPI ``Request`` (uses auth header then IP), a raw
    Authorization header string, or ``None`` which yields "local".
    Auth-derived hashes are 32 chars; IP-derived hashes are truncated to 12.
    """

    if source is None:
        return "local"
    if isinstance(source, str):
        return sha256(source.encode("utf-8")).hexdigest()[:32]
    auth = source.headers.get("Authorization")
    if auth:
        return sha256(auth.encode("utf-8")).hexdigest()[:32]
    ip = source.headers.get("X-Forwarded-For") or (
        source.client.host if source.client else None
    )
    if ip:
        return sha256(ip.encode("utf-8")).hexdigest()[:12]
    return uuid.uuid4().hex[:32]


async def trace_request(request: Request, call_next):
    rec = LogRecord(req_id=str(uuid.uuid4()))
    token_req = req_id_var.set(rec.req_id)
    token_rec = log_record_var.set(rec)
    rec.session_id = request.headers.get("X-Session-ID")
    rec.user_id = _anon_user_id(request)
    await user_store.ensure_user(rec.user_id)
    await user_store.increment_request(rec.user_id)
    rec.channel = request.headers.get("X-Channel")
    rec.received_at = utc_now().isoformat()
    rec.started_at = rec.received_at
    start_time = time.monotonic()
    response: Response | None = None
    try:
        response = await call_next(request)
        rec.status = "OK"
    except asyncio.TimeoutError:
        rec.status = "ERR_TIMEOUT"
        raise
    finally:
        rec.latency_ms = int((time.monotonic() - start_time) * 1000)
        await record_latency(rec.latency_ms)
        rec.p95_latency_ms = latency_p95()

        engine = rec.engine_used or "unknown"
        metrics.REQUEST_COUNT.labels(request.url.path, request.method, engine).inc()
        metrics.REQUEST_LATENCY.labels(
            request.url.path, request.method, engine
        ).observe(rec.latency_ms / 1000)
        if rec.cost_usd:
            metrics.REQUEST_COST.labels(
                request.url.path, request.method, engine
            ).observe(rec.cost_usd)

        if isinstance(response, Response):
            response.headers["X-Request-ID"] = rec.req_id

        await append_history(rec)
        log_record_var.reset(token_rec)
        req_id_var.reset(token_req)
    return response


async def reload_env_middleware(request: Request, call_next):
    load_env()
    return await call_next(request)
