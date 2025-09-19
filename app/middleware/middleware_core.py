import asyncio
import logging
import os
import time
import uuid
from hashlib import sha256

import jwt
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from ..env_utils import load_env
from ..security import jwt_decode

try:  # Optional dependency; provide a tiny fallback to avoid hard dep in tests
    from cachetools import TTLCache  # type: ignore
except Exception:  # pragma: no cover - fallback implementation
    from collections import OrderedDict

    class TTLCache:  # type: ignore
        def __init__(self, maxsize: int, ttl: float):
            self.maxsize = int(maxsize)
            self.ttl = float(ttl)
            self._data: dict[str, float] = {}
            self._order: OrderedDict[str, float] = OrderedDict()

        def _prune(self, now: float) -> None:
            # Remove expired entries
            expired = [k for k, ts in list(self._data.items()) if now - ts > self.ttl]
            for k in expired:
                self._data.pop(k, None)
                self._order.pop(k, None)
            # Enforce maxsize by evicting oldest
            while len(self._data) > self.maxsize and self._order:
                k, _ = self._order.popitem(last=False)
                self._data.pop(k, None)

        def get(self, key: str, default=None):
            now = time.monotonic()
            ts = self._data.get(key)
            if ts is None:
                return default
            if now - ts > self.ttl:
                # expired
                self._data.pop(key, None)
                self._order.pop(key, None)
                return default
            return ts

        def __setitem__(self, key: str, value: float) -> None:
            now = time.monotonic()
            self._data[key] = float(value)
            # maintain insertion order
            self._order.pop(key, None)
            self._order[key] = now
            self._prune(now)

        def __contains__(self, key: str) -> bool:  # pragma: no cover - convenience
            return self.get(key) is not None

        def __len__(self) -> int:  # pragma: no cover - convenience
            return len(self._data)


from ..logging_config import req_id_var

logger = logging.getLogger(__name__)
# Provider injection pattern - no direct imports of stores
from collections.abc import Callable
from typing import Any

from .. import metrics
from ..analytics import latency_p95, record_latency
from ..history import append_history
from ..otel_utils import get_trace_id_hex, observe_with_exemplar, start_span
from ..security import get_rate_limit_snapshot
from ..telemetry import LogRecord, log_record_var, utc_now

_user_store_provider: Callable[[], Any] | None = None


def set_store_providers(*, user_store_provider: Callable[[], Any]):
    """Set store providers for middleware. Called from main.py after app construction."""
    global _user_store_provider
    _user_store_provider = user_store_provider


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Let CORS handle preflight; do NOTHING here for OPTIONS
        if request.method == "OPTIONS":
            # Important: do not create your own response; just pass through
            # CORS middleware will handle the preflight response
            return await call_next(request)

        # Prefer client-provided ID to enable end-to-end correlation
        req_id = request.headers.get("X-Request-ID") or req_id_var.get()
        if not req_id or req_id == "-":
            req_id = str(uuid.uuid4())
            # Inject synthesized ID into request headers so downstream middlewares (e.g., Dedup) see it
            try:
                # Starlette headers are immutable mappings backed by raw list
                # Append lower-case header key and value bytes as per internal storage
                raw = list(getattr(request.headers, "raw", []))
                raw.append((b"x-request-id", req_id.encode("utf-8")))
                request.headers.__dict__["_list"] = raw
            except Exception:
                pass
        token = req_id_var.set(req_id)
        try:
            response = await call_next(request)
        finally:
            # Ensure response carries the same request id without overwriting existing value
            try:
                if isinstance(response, Response):
                    response.headers.setdefault("X-Request-ID", req_id)
            except Exception:
                pass
            req_id_var.reset(token)
        return response


class RedactHashMiddleware(BaseHTTPMiddleware):
    """Middleware that redacts sensitive headers and hashes sensitive values for logs."""

    SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key", "set-cookie"}

    async def dispatch(self, request: Request, call_next):
        # Make a shallow copy of headers for mutation
        try:
            raw = list(getattr(request.headers, "raw", []))
            new_raw = []
            for k, v in raw:
                key = k.decode() if isinstance(k, bytes) else str(k)
                val = v.decode() if isinstance(v, bytes) else str(v)
                if key.lower() in self.SENSITIVE_HEADERS:
                    # Keep a deterministic hash for correlation but don't log raw
                    try:
                        h = sha256(val.encode("utf-8")).hexdigest()
                        new_raw.append((k, f"[REDACTED_HASH:{h[:8]}]".encode()))
                    except Exception:
                        new_raw.append((k, b"[REDACTED]"))
                else:
                    new_raw.append((k, v))
            request.headers.__dict__["_list"] = new_raw
        except Exception:
            pass

        # Note: do NOT mutate request.cookies (breaking middleware) — keep redaction
        # limited to header/log contexts only. If cookie values need redaction for
        # logs, compute a redacted representation here without modifying the live
        # request.cookies mapping.
        try:
            _redacted_cookies = {}
            if hasattr(request, "cookies") and request.cookies:
                for name, val in list(request.cookies.items()):
                    try:
                        _redacted_cookies[name] = (
                            f"[REDACTED_HASH:{sha256(val.encode('utf-8')).hexdigest()[:8]}]"
                        )
                    except Exception:
                        _redacted_cookies[name] = "[REDACTED]"
            # attach for downstream logging/debugging only (non-authoritative)
            try:
                request.state._redacted_cookies = _redacted_cookies
            except Exception:
                pass
        except Exception:
            pass

        resp = await call_next(request)

        # Redact sensitive response headers for logging only, but do NOT remove
        # or overwrite Set-Cookie headers that the application relies on. Replace
        # only non-critical headers; preserve 'set-cookie' so browsers can receive
        # auth cookies during dev/test flows.
        try:
            for h in list(resp.headers.keys()):
                if h.lower() in self.SENSITIVE_HEADERS and h.lower() != "set-cookie":
                    resp.headers[h] = "[REDACTED]"
        except Exception:
            pass

        return resp


class HealthCheckFilterMiddleware(BaseHTTPMiddleware):
    """Filter out health check requests from access logs."""

    async def dispatch(self, request: Request, call_next):
        # Check if this is a health check request
        path = request.url.path
        if path.startswith("/healthz") or path.startswith("/health/"):
            # Skip logging for health checks
            response = await call_next(request)
            return response

        # For non-health check requests, proceed normally
        return await call_next(request)


class DedupMiddleware(BaseHTTPMiddleware):
    """Handle request deduplication and idempotency.

    Features:
    - Reject requests with repeated ``X-Request-ID`` header
    - Handle ``Idempotency-Key`` for POST/PUT/PATCH/DELETE requests
    - Cache full response (status, headers, body) for TTL window
    - Short-circuit duplicate requests early

    Configure via:
      • ``DEDUP_TTL_SECONDS`` (default: 60)
      • ``DEDUP_MAX_ENTRIES`` (default: 10000)
      • ``IDEMPOTENCY_TTL_SECONDS`` (default: 300, 5 minutes)
      • ``IDEMPOTENCY_CACHE_MAXSIZE`` (default: 10000)
    """

    def __init__(self, app):
        super().__init__(app)
        # TTL-bounded cache for X-Request-ID deduplication
        ttl_raw = float(os.getenv("DEDUP_TTL_SECONDS", "60"))
        max_raw = int(os.getenv("DEDUP_MAX_ENTRIES", "10000"))
        # Clamp to sane ranges to avoid misconfiguration foot-guns
        self._ttl: float = max(1.0, float(ttl_raw))
        self._max_entries: int = max(1, min(int(max_raw), 1_000_000))
        self._seen: TTLCache[str, float] = TTLCache(
            maxsize=self._max_entries, ttl=self._ttl
        )
        self._lock = asyncio.Lock()

        # Idempotency cache
        from app.middleware._cache import get_idempotency_store, make_idempotency_key

        idempotency_ttl_raw = float(
            os.getenv("IDEMPOTENCY_TTL_SECONDS", "300")
        )  # 5 minutes
        self._idempotency_store = get_idempotency_store()
        self._idempotency_ttl = idempotency_ttl_raw
        self._make_idempotency_key = make_idempotency_key
        logger.info(
            f"DedupMiddleware initialized: ttl={self._ttl}s, max_entries={self._max_entries}, idempotency_ttl={self._idempotency_ttl}s"
        )

    async def dispatch(self, request: Request, call_next):
        # Let CORS handle preflight; do NOTHING here for OPTIONS
        if request.method == "OPTIONS":
            # Important: do not create your own response; just pass through
            # CORS middleware will handle the preflight response
            return await call_next(request)

        now = time.monotonic()
        req_id = request.headers.get("X-Request-ID")

        # Handle X-Request-ID deduplication (existing behavior)
        if req_id:
            async with self._lock:
                ts = self._seen.get(req_id)
                if ts is not None:
                    # Compute remaining TTL for client hint
                    ttl_left = max(1, int(self._ttl - (now - float(ts))))
                    return Response(
                        "Duplicate request",
                        status_code=409,
                        headers={"Retry-After": str(ttl_left)},
                    )
                # Mark as in-flight to close the race window
                self._seen[req_id] = now

        # Handle Idempotency-Key for POST/PUT/PATCH/DELETE requests
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            logger.debug(
                "idempotency.key_present",
                extra={
                    "req_id": req_id or "unknown",
                    "key": idempotency_key[:8] + "...",  # Truncate for privacy
                    "method": request.method,
                    "path": request.url.path,
                },
            )

        # Process the request normally
        response = await call_next(request)

        # Cache response for idempotency if Idempotency-Key was provided
        if (
            idempotency_key
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and response.status_code < 500
        ):
            try:
                # Get user identity for cache key
                user_id = _anon_user_id(request)
                cache_key = self._make_idempotency_key(
                    request.method, request.url.path, idempotency_key, user_id
                )

                # For FastAPI/Starlette responses, we need to be careful about body access
                # The body might not be available yet or might be a streaming response
                response_body = b""
                if hasattr(response, "body") and response.body:
                    response_body = response.body
                elif hasattr(response, "body_iterator"):
                    # For streaming responses, we can't cache them
                    logger.debug(
                        "idempotency.cache_skipped",
                        extra={
                            "req_id": req_id or "unknown",
                            "reason": "streaming_response",
                        },
                    )
                    return response

                # Convert headers to dict
                headers_dict = {}
                if hasattr(response, "headers"):
                    for name, value in response.headers.items():
                        headers_dict[name] = value

                # Only cache if we have a body and it's not too large
                if response_body and len(response_body) < 1024 * 1024:  # 1MB limit
                    # Create cache entry
                    from app.middleware._cache import IdempotencyEntry

                    cache_entry = IdempotencyEntry(
                        status_code=response.status_code,
                        headers=headers_dict,
                        body=response_body,
                    )

                    # Store in cache
                    await self._idempotency_store.set(
                        cache_key, cache_entry, self._idempotency_ttl
                    )

                    logger.debug(
                        "idempotency.cache_stored",
                        extra={
                            "req_id": req_id or "unknown",
                            "cache_key": cache_key[:16] + "...",  # Truncate for privacy
                            "status_code": response.status_code,
                            "body_size": len(response_body),
                        },
                    )
                else:
                    logger.debug(
                        "idempotency.cache_skipped",
                        extra={
                            "req_id": req_id or "unknown",
                            "cache_key": cache_key[:16] + "...",  # Truncate for privacy
                            "reason": (
                                "no_body" if not response_body else "body_too_large"
                            ),
                        },
                    )

            except Exception as e:
                # Don't fail the request if caching fails
                logger.warning(
                    "idempotency.cache_store_failed",
                    extra={
                        "req_id": req_id or "unknown",
                        "error": str(e),
                    },
                )

        # Update X-Request-ID last seen time after completion
        if req_id:
            try:
                self._seen[req_id] = time.monotonic()
            except Exception:
                pass

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
    # Prefer Authorization hash when present for stability across IP changes
    auth = source.headers.get("Authorization")
    if auth:
        return sha256(auth.encode("utf-8")).hexdigest()[:32]
    # Use first IP from X-Forwarded-For if present
    xff = source.headers.get("X-Forwarded-For")
    ip = None
    if xff:
        ip = xff.split(",")[0].strip()
    elif source.client:
        ip = source.client.host
    if ip:
        return sha256(ip.encode("utf-8")).hexdigest()[:12]
    # Stable fallback rather than per-request random value
    return "anon"


class TraceRequestMiddleware(BaseHTTPMiddleware):
    """Trace/logging middleware — never stamp headers on OPTIONS (and strip if inherited)"""

    async def dispatch(self, request: Request, call_next):
        # Let CORS handle preflight; do NOTHING here for OPTIONS
        if request.method == "OPTIONS":
            # Important: do not create your own response; just pass through
            # CORS middleware will handle the preflight response
            return await call_next(request)

        # Unify request id across middlewares and response
        incoming_id = request.headers.get("X-Request-ID")
        current_id = req_id_var.get()
        req_id = incoming_id or (
            current_id if current_id and current_id != "-" else str(uuid.uuid4())
        )
        rec = LogRecord(req_id=req_id)
        token_req = req_id_var.set(req_id)
        token_rec = log_record_var.set(rec)

        # Set session/device ids if present
        rec.session_id = request.headers.get("X-Session-ID")
        rec.user_id = _anon_user_id(request)

        # Best-effort user accounting (do not affect request latency on failure)
        try:
            if _user_store_provider is not None:
                user_store = _user_store_provider()
                await user_store.ensure_user(rec.user_id)
                await user_store.increment_request(rec.user_id)
        except Exception:
            pass

        rec.channel = request.headers.get("X-Channel")
        rec.received_at = utc_now().isoformat()
        rec.started_at = rec.received_at
        start_time = time.monotonic()
        response: Response | None = None

        try:
            # Create a top-level span for the inbound request
            route = request.scope.get("route") if hasattr(request, "scope") else None
            route_path = getattr(route, "path", None) or request.url.path
            safe_target = getattr(request.url, "path", "/") or "/"

            with start_span(
                "http.request",
                {
                    "http.method": request.method,
                    "http.route": route_path,
                    "http.target": safe_target,
                    "user.anonymous_id": rec.user_id,
                    "http.request_id": req_id,
                    "http.origin": request.headers.get("Origin", ""),
                },
            ) as _span:
                # Redact sensitive headers into the span attributes for observability
                try:
                    if _span is not None and hasattr(_span, "set_attribute"):
                        _span.set_attribute("http.request_id", req_id)
                        _span.set_attribute("http.session_id", rec.session_id or "")
                        _span.set_attribute("env", os.getenv("ENV", ""))
                        _span.set_attribute(
                            "version",
                            os.getenv("APP_VERSION") or os.getenv("GIT_TAG") or "",
                        )
                except Exception:
                    pass
                # Remove sensitive headers before passing to app log context
                try:
                    if "authorization" in request.headers:
                        request.headers.__dict__["_list"] = [
                            (
                                k,
                                (
                                    v
                                    if k.decode().lower() != "authorization"
                                    else b"Bearer [REDACTED]"
                                ),
                            )
                            for (k, v) in request.headers.raw
                        ]
                except Exception:
                    pass

                response = await call_next(request)
                rec.status = "OK"

                # Enhanced tracing for golden trace endpoints
                status_code = getattr(response, "status_code", 200)
                try:
                    if _span is not None and hasattr(_span, "set_attribute"):
                        _span.set_attribute("http.status_code", status_code)

                        # Golden trace fields for whoami and auth/finish
                        if route_path in ["/v1/whoami", "/v1/auth/finish"]:
                            _span.set_attribute("http.rid", req_id)
                            _span.set_attribute("http.uid", rec.user_id)
                            _span.set_attribute(
                                "http.origin", request.headers.get("Origin", "")
                            )
                            _span.set_attribute("http.status", status_code)

                            # Set cookie flags for auth endpoints
                            if route_path == "/v1/auth/finish":
                                set_cookie_headers = response.headers.getlist(
                                    "set-cookie", []
                                )
                                cookie_flags = []
                                for cookie in set_cookie_headers:
                                    try:
                                        from ..web.cookies import NAMES

                                        if (
                                            "access_token" in cookie
                                            or NAMES.access in cookie
                                            or "refresh_token" in cookie
                                            or NAMES.refresh in cookie
                                        ):
                                            flags = []
                                            if "HttpOnly" in cookie:
                                                flags.append("HttpOnly")
                                            if "Secure" in cookie:
                                                flags.append("Secure")
                                    except Exception:
                                        if (
                                            "access_token" in cookie
                                            or "refresh_token" in cookie
                                        ):
                                            flags = []
                                            if "HttpOnly" in cookie:
                                                flags.append("HttpOnly")
                                            if "Secure" in cookie:
                                                flags.append("Secure")

                                    if "SameSite=" in cookie:
                                        samesite = cookie.split("SameSite=")[1].split(
                                            ";"
                                        )[0]
                                        flags.append(f"SameSite={samesite}")
                                    cookie_flags.extend(flags)
                                if cookie_flags:
                                    _span.set_attribute(
                                        "http.cookie_flags", " ".join(cookie_flags)
                                    )
                except Exception:
                    pass

                # Only stamp RL headers for non-OPTIONS requests
                # CORS preflight requests should never have rate limit headers
                if request.method != "OPTIONS":
                    try:
                        snap = get_rate_limit_snapshot(request)
                        if snap:
                            response.headers["ratelimit-limit"] = str(snap.get("limit"))
                            response.headers["ratelimit-remaining"] = str(
                                snap.get("remaining")
                            )
                            response.headers["ratelimit-reset"] = str(snap.get("reset"))
                            response.headers["X-RateLimit-Burst-Limit"] = str(
                                snap.get("burst_limit")
                            )
                            response.headers["X-RateLimit-Burst-Remaining"] = str(
                                snap.get("burst_remaining")
                            )
                            response.headers["X-RateLimit-Burst-Reset"] = str(
                                snap.get("burst_reset")
                            )
                    except Exception:
                        # Silently fail if rate limit snapshot fails
                        pass

            # Attach a compact logging meta for downstream log formatters and history
            # Include required fields: latency_ms, status_code, req_id, and router decision tag
            status_code = 0
            try:
                status_code = (
                    int(getattr(response, "status_code", 0))
                    if response is not None
                    else 0
                )
            except Exception:
                status_code = 0

            # Rate limit snapshot for visibility in logs
            try:
                snap = get_rate_limit_snapshot(request)
                limit_bucket = {
                    "long_limit": snap.get("limit"),
                    "long_remaining": snap.get("remaining"),
                    "burst_limit": snap.get("burst_limit"),
                    "burst_remaining": snap.get("burst_remaining"),
                }
            except Exception:
                limit_bucket = None

            # Scope info for logs
            try:
                payload = getattr(request.state, "jwt_payload", None)
                scopes = []
                if isinstance(payload, dict):
                    raw_scopes = payload.get("scope") or payload.get("scopes") or []
                    scopes = (
                        raw_scopes.split()
                        if isinstance(raw_scopes, str)
                        else [str(s) for s in raw_scopes]
                    )
            except Exception:
                scopes = []

            meta = {
                "req_id": rec.req_id,
                "status_code": status_code,
                "latency_ms": rec.latency_ms,
                "router_decision": rec.route_reason,
                "model_used": rec.model_name,
                "reason": rec.route_reason,
                "rule": rec.route_reason,  # duplicate for dashboard filters
                "tokens_in": rec.prompt_tokens,
                "tokens_out": rec.completion_tokens,
                "retrieved_tokens": rec.retrieved_tokens,
                "self_check": rec.self_check_score,
                "escalated": rec.escalated,
                "cache_hit": rec.cache_hit,
                "limit_bucket": limit_bucket,
                "requests_remaining": (
                    (limit_bucket or {}).get("long_remaining")
                    if isinstance(limit_bucket, dict)
                    else None
                ),
                "enforced_scope": " ".join(sorted(set(scopes))) if scopes else None,
                # Structured fields
                "user_id": getattr(request.state, "user_id", None) or rec.user_id,
                "route": route_path,
                "error_code": (
                    getattr(
                        getattr(response, "body_iterator", None), "status_code", None
                    )
                    or None
                ),
            }

            try:
                # Skip logging for health check requests
                if route_path.startswith("/healthz") or route_path.startswith(
                    "/health/"
                ):
                    pass
                else:
                    # log via std logging for live dashboards then persist in history
                    import logging
                    import random as _rand

                    env = os.getenv("ENV", "").strip().lower()
                    status_family = (status_code // 100) if status_code else 0
                    # Sample successes in prod; log all non-2xx
                    p = 1.0
                    if env in {"prod", "production"} and status_family == 2:
                        try:
                            p = float(os.getenv("OBS_SAMPLE_SUCCESS_RATE", "0.1"))
                        except Exception:
                            p = 0.1
                    if status_family != 2 or _rand.random() < p:
                        logging.getLogger(__name__).info(
                            "request_summary", extra={"meta": meta}
                        )
            except Exception:
                pass

            # Persist structured history (skip health checks)
            if not (
                route_path.startswith("/healthz") or route_path.startswith("/health/")
            ):
                full = {**rec.model_dump(exclude_none=True), **{"meta": meta}}
                try:
                    asyncio.create_task(append_history(full))
                except Exception:
                    pass

            # Record latency and metrics
            rec.latency_ms = int((time.monotonic() - start_time) * 1000)
            await record_latency(rec.latency_ms)
            try:
                rec.p95_latency_ms = latency_p95()
            except Exception:
                rec.p95_latency_ms = 0

            engine = rec.engine_used or "unknown"
            route = request.scope.get("route") if hasattr(request, "scope") else None
            route_path = getattr(route, "path", None) or request.url.path

            try:
                metrics.REQUEST_COUNT.labels(route_path, request.method, engine).inc()
            except Exception:
                pass

            # Emit canonical counters/histograms too
            try:
                metrics.GESAHNI_REQUESTS_TOTAL.labels(
                    route_path, request.method, str(status_code or 0)
                ).inc()
            except Exception:
                pass

            # PHASE 6: Enhanced scope-based metrics and SLO tracking
            try:
                # Track per-scope metrics if user has scopes
                user_scopes = getattr(request.state, "scopes", None)
                if user_scopes:
                    for scope in user_scopes:
                        metrics.SCOPE_REQUESTS_TOTAL.labels(
                            scope, route_path, request.method, str(status_code or 0)
                        ).inc()
                        metrics.SCOPE_LATENCY_SECONDS.labels(
                            scope, route_path, request.method
                        ).observe(rec.latency_ms / 1000)

                # Track auth failures
                if status_code in (401, 403, 429):
                    failure_type = str(status_code)
                    reason = getattr(request.state, "auth_failure_reason", "unknown")
                    metrics.AUTH_FAILURES_TOTAL.labels(
                        failure_type, route_path, reason
                    ).inc()

                # Track scope usage for authorization decisions
                if hasattr(request.state, "scope_check_results"):
                    for scope, result in request.state.scope_check_results.items():
                        metrics.SCOPE_USAGE_TOTAL.labels(
                            scope, route_path, result
                        ).inc()

                # PHASE 6: Record SLO measurements
                from app.slos import record_api_request

                auth_success = status_code not in (401, 403, 429)
                record_api_request(
                    status_code,
                    rec.latency_ms,
                    auth_success,
                    route=route_path,
                    method=request.method,
                )

            except Exception:
                pass  # Continue even if enhanced metrics/SLO tracking fails

            # Observe with exemplar when possible to jump from Grafana to trace
            try:
                trace_id = get_trace_id_hex()
                hist = metrics.REQUEST_LATENCY.labels(
                    route_path, request.method, engine
                )
                observe_with_exemplar(
                    hist,
                    rec.latency_ms / 1000,
                    exemplar_labels={"trace_id": trace_id} if trace_id else None,
                )
            except Exception:
                try:
                    metrics.REQUEST_LATENCY.labels(
                        route_path, request.method, engine
                    ).observe(rec.latency_ms / 1000)
                except Exception:
                    pass

            try:
                metrics.GESAHNI_LATENCY_SECONDS.labels(route_path).observe(
                    rec.latency_ms / 1000
                )
            except Exception:
                pass

            if rec.prompt_cost_usd:
                metrics.REQUEST_COST.labels(
                    route_path, request.method, engine, "prompt"
                ).observe(rec.prompt_cost_usd)
            if rec.completion_cost_usd:
                metrics.REQUEST_COST.labels(
                    route_path, request.method, engine, "completion"
                ).observe(rec.completion_cost_usd)
            if rec.cost_usd:
                metrics.REQUEST_COST.labels(
                    route_path, request.method, engine, "total"
                ).observe(rec.cost_usd)

            if isinstance(response, Response):
                response.headers.setdefault("X-Request-ID", rec.req_id)
                # Surface current trace id in responses when available
                try:
                    tid = get_trace_id_hex()
                    if tid:
                        response.headers["X-Trace-ID"] = tid
                        # Optional hint for browser devtools
                        response.headers.setdefault(
                            "Server-Timing", f"traceparent;desc={tid}"
                        )
                except Exception:
                    pass

                # Mark model fallback headers for observability (e.g., llama→gpt)
                try:
                    rr = rec.route_reason or ""
                    if rr and "fallback_from_llama" in rr:
                        response.headers.setdefault("X-Fallback", "gpt")
                except Exception:
                    pass

                # Make backend origin explicit for debugging across the Next proxy
                try:
                    response.headers.setdefault("X-Debug-Backend", "fastapi")
                except Exception:
                    pass

                # Security headers: HSTS, CSP and other hardening headers
                try:
                    env = os.getenv("ENV", "").strip().lower()
                    if request.url.scheme == "https" and env in {"prod", "production"}:
                        response.headers.setdefault(
                            "Strict-Transport-Security",
                            "max-age=63072000; includeSubDomains; preload",
                        )
                    # Security headers (CSP handled by frontend)
                    response.headers.setdefault("Referrer-Policy", "no-referrer")
                    response.headers.setdefault("X-Content-Type-Options", "nosniff")
                    response.headers.setdefault(
                        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
                    )
                    response.headers.setdefault("X-Frame-Options", "DENY")
                except Exception:
                    pass

                # Offline mode badge for UI: set a cookie when local fallback is in use
                try:
                    from .llama_integration import LLAMA_HEALTHY as _LL_OK

                    local_mode = (not _LL_OK) and (
                        os.getenv("OPENAI_API_KEY", "") == ""
                    )
                    if local_mode:
                        # Enforce Secure/SameSite in prod; relax in tests/dev (http)
                        secure = True
                        try:
                            if getattr(request.url, "scheme", "http") != "https":
                                secure = False
                        except Exception:
                            pass
                        # Use centralized cookie functions for local mode indicator
                        from ..web.cookies import set_named_cookie

                        set_named_cookie(
                            resp=response,
                            name="X-Local-Mode",
                            value="1",
                            ttl=600,
                            httponly=True,
                            secure=secure,
                            samesite="Lax",  # Keep Lax for local mode indicator
                        )
                except Exception:
                    pass

        except TimeoutError:
            rec.status = "ERR_TIMEOUT"
            raise
        except Exception:
            # Ensure status reflects generic failures
            rec.status = "ERR_EXCEPTION"
            raise
        finally:
            log_record_var.reset(token_rec)
            req_id_var.reset(token_req)

        return response


async def silent_refresh_middleware(request: Request, call_next):
    """Rotate access and refresh cookies server-side when nearing expiry.

    Controlled via env:
      - JWT_SECRET: required to decode/encode
      - JWT_ACCESS_TTL_SECONDS: lifetime of new tokens (default 14d)
      - ACCESS_REFRESH_THRESHOLD_SECONDS: refresh when exp - now < threshold (default 3600s)
      - DISABLE_SILENT_REFRESH: set to "1" to disable this middleware
    """
    # Check if silent refresh is disabled via environment variable
    if os.getenv("DISABLE_SILENT_REFRESH", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        logger.debug("SILENT_REFRESH: Disabled via environment variable")
        return await call_next(request)

    logger.debug("SILENT_REFRESH: Middleware called")
    # Call downstream first; do not swallow exceptions from handlers
    response: Response = await call_next(request)

    # Best-effort refresh; never raise from middleware
    try:
        # Skip static and non-API paths to avoid unnecessary token work
        try:
            path = request.url.path or ""
            logger.debug("SILENT_REFRESH: Processing path %s", path)
            if not path.startswith("/v1"):
                logger.debug("SILENT_REFRESH: Skipping non-v1 path")
                return response
            # Skip logout endpoints to avoid setting new cookies during logout
            # Broadened: skip any path that is logout-ish (ends with /logout or contains /auth/logout), regardless of status code
            if (
                path.endswith("/logout")
                or "/auth/logout" in path
                or request.headers.get("X-Logout") == "true"
            ):
                logger.debug("SILENT_REFRESH: Skipping logout path or X-Logout header")
                return response
            # Skip refresh if the response includes any Set-Cookie that deletes an auth cookie
            # (access_token, refresh_token, or __session)—i.e., a delete with Max-Age=0
            set_cookies = response.headers.getlist("set-cookie", [])
            try:
                from ..web.cookies import NAMES

                auth_cookies = [
                    "access_token",
                    "refresh_token",
                    "__session",
                    NAMES.access,
                    NAMES.refresh,
                    NAMES.session,
                ]
            except Exception:
                auth_cookies = ["access_token", "refresh_token", "__session"]
            if any(
                any(cookie in h and "Max-Age=0" in h for cookie in auth_cookies)
                for h in set_cookies
            ):
                logger.debug(
                    "SILENT_REFRESH: Skipping due to auth cookie deletion (Max-Age=0)"
                )
                return response
            # Skip on 204 responses
            if response.status_code == 204:
                logger.debug("SILENT_REFRESH: Skipping due to 204 status code")
                return response
        except Exception:
            pass
        # Accept both canonical and legacy cookie names for access token
        from ..web.cookies import read_access_cookie, read_refresh_cookie

        token = read_access_cookie(request)
        refresh_token = read_refresh_cookie(request)
        secret = os.getenv("JWT_SECRET")

        # Validation logging: initial state
        had_at = bool(token)
        had_rt = bool(refresh_token)
        logger.debug(f"SILENT_REFRESH: had_at={had_at} had_rt={had_rt}")

        # If no access token but refresh token exists, perform cold-boot refresh
        if not token and refresh_token and secret:
            logger.debug(
                "SILENT_REFRESH: Cold-boot scenario - no access token but refresh token present"
            )
            # Use perform_lazy_refresh for cold-boot scenario
            try:
                from ..auth_refresh import perform_lazy_refresh

                # Get user_id from refresh token if possible, otherwise use anon
                user_id = "anon"
                try:
                    from ..tokens import decode_jwt_token

                    rt_payload = decode_jwt_token(refresh_token)
                    if rt_payload and str(rt_payload.get("type") or "") == "refresh":
                        user_id = str(
                            rt_payload.get("sub") or rt_payload.get("user_id") or "anon"
                        )
                except Exception:
                    pass

                if user_id != "anon":
                    await perform_lazy_refresh(request, response, user_id)
                    logger.debug("SILENT_REFRESH: Cold-boot refresh completed")
                return response
            except Exception as e:
                logger.debug(f"SILENT_REFRESH: Cold-boot refresh failed: {e}")
                return response

        if not token or not secret:
            return response
        # Decode without hard-failing on expiry/format
        try:
            payload = jwt_decode(token, secret, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            payload = None
        except Exception:
            payload = None
        if not payload:
            return response
        now = int(time.time())
        exp = int(payload.get("exp", 0))
        threshold = int(os.getenv("ACCESS_REFRESH_THRESHOLD_SECONDS", "3600"))
        logger.debug(
            "SILENT_REFRESH: Token expires in %s seconds, threshold is %s",
            exp - now,
            threshold,
        )
        should_refresh = exp - now <= threshold
        logger.debug(
            f"SILENT_REFRESH: should_refresh={should_refresh} (exp={exp} now={now} threshold={threshold})"
        )
        if should_refresh:
            logger.debug("SILENT_REFRESH: Token needs refresh, proceeding...")
            # Small jitter to avoid stampede when many tabs refresh concurrently
            try:
                import asyncio as _asyncio
                import random as _rand

                await _asyncio.sleep(_rand.uniform(0.01, 0.05))
            except Exception:
                pass
            # Rotate token, preserving custom claims
            user_id = str(payload.get("user_id") or "")
            if not user_id:
                return response
            # Use centralized TTL from tokens.py
            from ..tokens import get_default_access_ttl

            lifetime = get_default_access_ttl()
            base_claims = {
                k: v
                for k, v in payload.items()
                if k not in {"iat", "exp", "nbf", "jti"}
            }
            base_claims["user_id"] = user_id
            # Use tokens.py facade instead of direct JWT encoding
            from ..tokens import make_access

            new_token = make_access({"user_id": user_id}, ttl_s=lifetime)
            # Use centralized cookie configuration
            from ..cookie_config import get_cookie_config, get_token_ttls

            cookie_config = get_cookie_config(request)
            access_ttl, _ = get_token_ttls()

            # Use centralized cookie functions for access token
            from ..web.cookies import set_auth_cookies

            # For silent refresh, we only update the access token, keep existing refresh token
            # and don't set session cookie (it should already exist)
            set_auth_cookies(
                response,
                access=new_token,
                refresh=None,
                session_id=None,
                access_ttl=access_ttl,
                refresh_ttl=0,
                request=request,
            )
            # Optionally extend refresh cookie if present (best-effort) with jitter to avoid herd
            try:
                rtok = read_refresh_cookie(request)
                if rtok:
                    rp = jwt_decode(rtok, secret, algorithms=["HS256"])  # may raise
                    r_exp = int(rp.get("exp", now))
                    import random as _rand

                    # Jitter extension by 50–250ms only; do not reduce lifespan substantially
                    r_life = max(0, r_exp - now)
                    if r_life > 0:
                        # Jitter write ordering
                        try:
                            await asyncio.sleep(_rand.uniform(0.01, 0.05))  # type: ignore[name-defined]
                        except Exception:
                            pass
                        # For refresh token extension, we need to set it individually
                        # since set_auth_cookies expects both access and refresh tokens
                        try:
                            from ..web.cookies import NAMES, set_named_cookie

                            set_named_cookie(
                                resp=response,
                                name=NAMES.refresh,
                                value=rtok,
                                ttl=r_life,
                                httponly=cookie_config["httponly"],
                            )
                        except Exception:
                            # Fallback to centralized cookie functions
                            from ..web.cookies import set_auth_cookies

                            # For refresh token extension, we need to set it individually
                            # since set_auth_cookies expects both access and refresh tokens
                            set_auth_cookies(
                                response,
                                access="",
                                refresh=rtok,
                                session_id=None,
                                access_ttl=0,
                                refresh_ttl=r_life,
                                request=request,
                            )
            except Exception:
                pass

        # Validation logging: results
        try:
            set_cookie_count = len(response.headers.getlist("set-cookie", []))
            new_at = bool(new_token) if "new_token" in locals() else False
            new_rt = bool(rtok) if "rtok" in locals() else False
            logger.debug(
                f"SILENT_REFRESH: new_at={new_at} new_rt={new_rt} set_cookie_count={set_cookie_count}"
            )
        except Exception:
            pass  # Best-effort logging

    except Exception:
        # best-effort; never fail request due to refresh
        pass
    return response


async def reload_env_middleware(request: Request, call_next):
    # Check if middleware is disabled (useful for tests)
    if os.getenv("DISABLE_ENV_RELOAD_MW") == "1":
        return await call_next(request)

    # Only reload env when explicitly enabled (e.g., in dev)
    try:
        if os.getenv(
            "RELOAD_ENV_ON_REQUEST", os.getenv("ENV_RELOAD_ON_REQUEST", "0")
        ).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            load_env()
    except Exception:
        pass
    return await call_next(request)


class APILoggingMiddleware(BaseHTTPMiddleware):
    """Comprehensive API request/response logging middleware."""

    def __init__(self, app, exclude_paths=None, exclude_methods=None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or ["/health", "/metrics", "/favicon.ico"]
        self.exclude_methods = exclude_methods or ["OPTIONS"]
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, request: Request, call_next):
        # Skip logging for excluded paths and methods
        if request.url.path in self.exclude_paths or request.method in self.exclude_methods:
            return await call_next(request)

        # Start timing
        start_time = time.time()
        request_id = getattr(request.state, 'req_id', None) or str(uuid.uuid4())[:8]

        # Extract comprehensive request details
        method = request.method
        path = request.url.path
        query = str(request.url.query)
        full_url = str(request.url)
        user_agent = request.headers.get("User-Agent", "unknown")
        content_type = request.headers.get("Content-Type", "unknown")
        content_length = request.headers.get("Content-Length", "0")
        origin = request.headers.get("Origin", "none")
        referer = request.headers.get("Referer", "none")
        authorization = "present" if request.headers.get("Authorization") else "absent"
        csrf_token = "present" if request.headers.get("X-CSRF-Token") else "absent"
        cookie_header = "present" if request.headers.get("Cookie") else "absent"
        cookie_count = len(request.cookies) if hasattr(request, 'cookies') else 0

        # Extract client info
        client_ip = (
            request.headers.get("X-Forwarded-For") or
            request.headers.get("X-Real-IP") or
            getattr(request.client, 'host', 'unknown') if request.client else 'unknown'
        )
        client_port = getattr(request.client, 'port', 'unknown') if request.client else 'unknown'

        # Determine request category
        is_auth_endpoint = any(auth_path in path for auth_path in ['/auth/', '/login', '/logout', '/whoami', '/csrf'])
        is_debug_endpoint = '/debug/' in path
        is_health_endpoint = '/health' in path
        is_api_endpoint = path.startswith('/v1/')

        category = "auth" if is_auth_endpoint else "debug" if is_debug_endpoint else "health" if is_health_endpoint else "api" if is_api_endpoint else "other"
        category_emoji = "🔐" if category == "auth" else "🔍" if category == "debug" else "💚" if category == "health" else "🔗" if category == "api" else "📄"

        # Ultra-detailed request logging
        self.logger.info(f"{category_emoji} API_REQUEST #{request_id}", extra={
            "request_id": request_id,
            "method": method,
            "path": path,
            "full_url": full_url,
            "query": query if query else "none",
            "category": category,
            "user_agent": user_agent,
            "content_type": content_type,
            "content_length": content_length,
            "origin": origin,
            "referer": referer,
            "authorization": authorization,
            "csrf_token": csrf_token,
            "cookie_header": cookie_header,
            "cookie_count": cookie_count,
            "client_ip": client_ip,
            "client_port": client_port,
            "headers_count": len(dict(request.headers)),
            "is_cors_request": bool(origin),
            "is_authenticated_request": authorization == "present",
            "timestamp": time.time(),
            "start_time": start_time
        })

        # Special detailed logging for auth requests
        if is_auth_endpoint:
            self.logger.info(f"🔐 AUTH_REQUEST_DETAILS #{request_id}", extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "has_authorization_header": authorization == "present",
                "has_csrf_token": csrf_token == "present",
                "has_cookies": cookie_header == "present",
                "cookie_names": list(request.cookies.keys()) if hasattr(request, 'cookies') else [],
                "origin": origin,
                "referer": referer,
                "user_agent": user_agent,
                "client_ip": client_ip,
                "timestamp": time.time()
            })

        try:
            # Process the request
            response = await call_next(request)

            # Calculate response time
            response_time = time.time() - start_time

            # Extract comprehensive response details
            status_code = response.status_code
            response_content_type = response.headers.get("Content-Type", "unknown")
            response_content_length = response.headers.get("Content-Length", "unknown")
            response_x_request_id = response.headers.get("X-Request-ID", "none")
            response_x_csrf_token = "present" if response.headers.get("X-CSRF-Token") else "absent"
            response_set_cookie = "present" if response.headers.get("Set-Cookie") else "absent"
            response_cache_control = response.headers.get("Cache-Control", "none")

            # Determine log level and emoji based on status code
            if status_code >= 500:
                log_level = logging.ERROR
                status_emoji = "🚨"
                status_category = "server_error"
            elif status_code >= 400:
                log_level = logging.WARNING
                status_emoji = "⚠️"
                status_category = "client_error"
            elif status_code >= 300:
                log_level = logging.INFO
                status_emoji = "🔄"
                status_category = "redirect"
            else:
                log_level = logging.INFO
                status_emoji = "✅"
                status_category = "success"

            # Performance categorization
            if response_time > 5.0:
                perf_category = "very_slow"
                perf_emoji = "🐌🐌"
            elif response_time > 2.0:
                perf_category = "slow"
                perf_emoji = "🐌"
            elif response_time > 1.0:
                perf_category = "medium"
                perf_emoji = "🟡"
            elif response_time > 0.5:
                perf_category = "fast"
                perf_emoji = "⚡"
            else:
                perf_category = "very_fast"
                perf_emoji = "🚀"

            # Ultra-detailed response logging
            self.logger.log(log_level, f"{status_emoji}{perf_emoji} API_RESPONSE #{request_id}", extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "category": category,
                "status_code": status_code,
                "status_category": status_category,
                "response_time_ms": round(response_time * 1000, 2),
                "performance": perf_category,
                "content_type": response_content_type,
                "content_length": response_content_length,
                "x_request_id": response_x_request_id,
                "x_csrf_token": response_x_csrf_token,
                "set_cookie": response_set_cookie,
                "cache_control": response_cache_control,
                "client_ip": client_ip,
                "is_auth_response": is_auth_endpoint,
                "is_debug_response": is_debug_endpoint,
                "timestamp": time.time(),
                "response_time": response_time,
                "start_time": start_time
            })

            # Special detailed logging for auth responses
            if is_auth_endpoint:
                set_cookie_details = []
                if response_set_cookie == "present":
                    # Try to parse set-cookie headers (basic parsing)
                    set_cookie_raw = response.headers.get("Set-Cookie", "")
                    if isinstance(set_cookie_raw, str):
                        cookie_parts = set_cookie_raw.split(';')
                        if cookie_parts:
                            cookie_name_value = cookie_parts[0].strip()
                            cookie_flags = cookie_parts[1:] if len(cookie_parts) > 1 else []
                            set_cookie_details.append({
                                "name_value": cookie_name_value,
                                "flags": cookie_flags,
                                "is_http_only": any('httponly' in f.lower() for f in cookie_flags),
                                "is_secure": any('secure' in f.lower() for f in cookie_flags),
                                "max_age": next((f.split('=')[1] for f in cookie_flags if f.lower().startswith('max-age=')), 'session')
                            })

                self.logger.info(f"🔐 AUTH_RESPONSE_DETAILS #{request_id}", extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "response_time_ms": round(response_time * 1000, 2),
                    "x_csrf_token": response_x_csrf_token,
                    "set_cookie": response_set_cookie,
                    "set_cookie_details": set_cookie_details,
                    "cache_control": response_cache_control,
                    "client_ip": client_ip,
                    "timestamp": time.time()
                })

            # Log performance warnings for slow requests
            if response_time > 2.0:  # More than 2 seconds
                self.logger.warning(f"🐌 SLOW_API_REQUEST #{request_id}", extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "response_time_ms": round(response_time * 1000, 2),
                    "performance": perf_category,
                    "category": category,
                    "content_type": response_content_type,
                    "client_ip": client_ip,
                    "user_agent": user_agent[:50] + "..." if len(user_agent) > 50 else user_agent,
                    "is_auth_endpoint": is_auth_endpoint,
                    "timestamp": time.time(),
                })

            # Log detailed error information for 4xx/5xx responses
            if status_code >= 400:
                self.logger.log(log_level, f"❌ API_ERROR_RESPONSE #{request_id}", extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "status_category": status_category,
                    "response_time_ms": round(response_time * 1000, 2),
                    "content_type": response_content_type,
                    "content_length": response_content_length,
                    "client_ip": client_ip,
                    "user_agent": user_agent,
                    "origin": origin,
                    "referer": referer,
                    "authorization": authorization,
                    "csrf_token": csrf_token,
                    "category": category,
                    "is_cors_request": bool(origin),
                    "timestamp": time.time()
                })

            return response

        except Exception as e:
            # Calculate error response time
            error_time = time.time() - start_time

            # Ultra-detailed error logging
            import traceback

            # Extract error details
            error_message = str(e)
            error_type = type(e).__name__
            error_module = getattr(type(e), '__module__', 'unknown')
            error_full_name = f"{error_module}.{error_type}" if error_module != 'builtins' else error_type

            # Get stack trace
            stack_trace = traceback.format_exc()

            # Determine error severity
            is_critical_error = any(critical in error_type.lower() for critical in ['internal', 'server', 'database', 'connection'])
            error_severity = "critical" if is_critical_error else "standard"

            # Log comprehensive error information
            self.logger.error(f"🚨💥 API_EXCEPTION #{request_id} [{error_severity.upper()}]", extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "category": category,
                "error_message": error_message,
                "error_type": error_type,
                "error_full_name": error_full_name,
                "error_module": error_module,
                "error_severity": error_severity,
                "response_time_ms": round(error_time * 1000, 2),
                "client_ip": client_ip,
                "client_port": client_port,
                "user_agent": user_agent,
                "origin": origin,
                "referer": referer,
                "authorization": authorization,
                "csrf_token": csrf_token,
                "cookie_header": cookie_header,
                "cookie_count": cookie_count,
                "is_cors_request": bool(origin),
                "is_authenticated_request": authorization == "present",
                "stack_trace_lines": len(stack_trace.split('\n')) if stack_trace else 0,
                "has_stack_trace": bool(stack_trace),
                "timestamp": time.time(),
                "start_time": start_time
            })

            # Log stack trace separately for better readability
            if stack_trace:
                self.logger.error(f"📋 EXCEPTION_STACK_TRACE #{request_id}", extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "error_type": error_type,
                    "stack_trace": stack_trace[:2000] + "..." if len(stack_trace) > 2000 else stack_trace,
                    "timestamp": time.time()
                })

            # Log additional context for auth-related errors
            if is_auth_endpoint:
                self.logger.error(f"🔐 AUTH_EXCEPTION_CONTEXT #{request_id}", extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "error_type": error_type,
                    "error_message": error_message,
                    "cookie_names": list(request.cookies.keys()) if hasattr(request, 'cookies') else [],
                    "has_authorization_header": authorization == "present",
                    "has_csrf_token": csrf_token == "present",
                    "client_ip": client_ip,
                    "timestamp": time.time()
                })

            # Log performance context for slow errors
            if error_time > 1.0:
                self.logger.warning(f"🐌 SLOW_EXCEPTION #{request_id}", extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "error_type": error_type,
                    "error_time_ms": round(error_time * 1000, 2),
                    "category": category,
                    "client_ip": client_ip,
                    "timestamp": time.time()
                })

            # Re-raise the exception to let error handling middleware handle it
            raise
