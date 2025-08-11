import uuid
import asyncio
import time
import os
from hashlib import sha256

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from .logging_config import req_id_var
from .telemetry import LogRecord, log_record_var, utc_now
from .decisions import add_decision, add_trace_event
from .history import append_history
from .analytics import record_latency, latency_p95
from .user_store import user_store
from .env_utils import load_env
from . import metrics
from .security import get_rate_limit_snapshot


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = str(uuid.uuid4())
        token = req_id_var.set(req_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        req_id_var.reset(token)
        return response


class DedupMiddleware(BaseHTTPMiddleware):
    """Reject requests with a repeated ``X-Request-ID`` header.

    To avoid unbounded memory growth, seen IDs are retained only for a short
    time‑to‑live and optionally capped by a maximum set size. Configure via:
      • ``DEDUP_TTL_SECONDS`` (default: 60)
      • ``DEDUP_MAX_ENTRIES`` (default: 10000)
    """

    def __init__(self, app):
        super().__init__(app)
        # Map of request id -> last seen monotonic timestamp
        self._seen: dict[str, float] = {}
        self._ttl: float = float(os.getenv("DEDUP_TTL_SECONDS", "60"))
        self._max_entries: int = int(os.getenv("DEDUP_MAX_ENTRIES", "10000"))

    async def dispatch(self, request: Request, call_next):
        now = time.monotonic()
        # Prune expired ids
        if self._seen:
            expired = [rid for rid, ts in self._seen.items() if now - ts > self._ttl]
            for rid in expired:
                self._seen.pop(rid, None)

        req_id = request.headers.get("X-Request-ID")
        if req_id and req_id in self._seen:
            return Response("Duplicate request", status_code=409)

        response = await call_next(request)

        if req_id:
            self._seen[req_id] = now
            # Soft cap: if we exceed max entries, keep only the newest half
            if len(self._seen) > self._max_entries:
                # Sort by timestamp descending and keep the most recent half
                keep = sorted(self._seen.items(), key=lambda kv: kv[1], reverse=True)[
                    : max(1, self._max_entries // 2)
                ]
                self._seen = dict(keep)
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
        if rec.prompt_cost_usd:
            metrics.REQUEST_COST.labels(
                request.url.path, request.method, engine, "prompt"
            ).observe(rec.prompt_cost_usd)
        if rec.completion_cost_usd:
            metrics.REQUEST_COST.labels(
                request.url.path, request.method, engine, "completion"
            ).observe(rec.completion_cost_usd)
        if rec.cost_usd:
            metrics.REQUEST_COST.labels(
                request.url.path, request.method, engine, "total"
            ).observe(rec.cost_usd)

        if isinstance(response, Response):
            response.headers["X-Request-ID"] = rec.req_id
            # Offline mode badge for UI: set a cookie when local fallback is in use
            try:
                from .llama_integration import LLAMA_HEALTHY as _LL_OK
                local_mode = (not _LL_OK) and (os.getenv("OPENAI_API_KEY", "") == "")
                if local_mode:
                    response.set_cookie("X-Local-Mode", "1", max_age=600, path="/")
            except Exception:
                pass
            # Rate limit visibility headers
            try:
                snap = get_rate_limit_snapshot(request)
                response.headers["X-RateLimit-Limit"] = str(snap.get("limit"))
                response.headers["X-RateLimit-Remaining"] = str(snap.get("remaining"))
                response.headers["X-RateLimit-Reset"] = str(snap.get("reset"))
                response.headers["X-RateLimit-Burst-Limit"] = str(snap.get("burst_limit"))
                response.headers["X-RateLimit-Burst-Remaining"] = str(snap.get("burst_remaining"))
                response.headers["X-RateLimit-Burst-Reset"] = str(snap.get("burst_reset"))
            except Exception:
                pass

        # Attach a compact logging meta for downstream log formatters and history
        meta = {
            "model_used": rec.model_name,
            "reason": rec.route_reason,
            "rule": rec.route_reason,  # duplicate for dashboard filters
            "tokens_in": rec.prompt_tokens,
            "tokens_out": rec.completion_tokens,
            "retrieved_tokens": rec.retrieved_tokens,
            "latency_ms": rec.latency_ms,
            "self_check": rec.self_check_score,
            "escalated": rec.escalated,
            "cache_hit": rec.cache_hit,
        }
        try:
            # log via std logging for live dashboards then persist in history
            import logging

            logging.getLogger(__name__).info("request_summary", extra={"meta": meta})
        except Exception:
            pass
        # Persist structured history
        full = {**rec.model_dump(exclude_none=True), **{"meta": meta}}
        await append_history(full)
        # Also store a compact decision record for admin UI and explain endpoint
        try:
            add_decision(full)
        except Exception:
            pass
        # Ensure at least a minimal trace exists
        try:
            add_trace_event(rec.req_id, "request_end", status=rec.status, latency_ms=rec.latency_ms)
        except Exception:
            pass
        log_record_var.reset(token_rec)
        req_id_var.reset(token_req)
    return response


async def reload_env_middleware(request: Request, call_next):
    load_env()
    return await call_next(request)
