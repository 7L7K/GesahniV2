import uuid
import asyncio
import time
import os
from hashlib import sha256

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import jwt
try:  # Optional dependency; provide a tiny fallback to avoid hard dep in tests
    from cachetools import TTLCache  # type: ignore
except Exception:  # pragma: no cover - fallback implementation
    from collections import OrderedDict

    class TTLCache:  # type: ignore
        def __init__(self, maxsize: int, ttl: float):
            self.maxsize = int(maxsize)
            self.ttl = float(ttl)
            self._data: dict[str, float] = {}
            self._order: "OrderedDict[str, float]" = OrderedDict()

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

import logging
from .logging_config import req_id_var

logger = logging.getLogger(__name__)
from .telemetry import LogRecord, log_record_var, utc_now
from .decisions import add_decision, add_trace_event
from .history import append_history
from .analytics import record_latency, latency_p95
from .otel_utils import get_trace_id_hex, observe_with_exemplar, start_span
from .user_store import user_store
from .env_utils import load_env
from . import metrics
from .security import get_rate_limit_snapshot


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
                        _redacted_cookies[name] = f"[REDACTED_HASH:{sha256(val.encode('utf-8')).hexdigest()[:8]}]"
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
        if path.startswith('/healthz') or path.startswith('/health/'):
            # Skip logging for health checks
            response = await call_next(request)
            return response
        
        # For non-health check requests, proceed normally
        return await call_next(request)


class DedupMiddleware(BaseHTTPMiddleware):
    """Reject requests with a repeated ``X-Request-ID`` header.

    To avoid unbounded memory growth, seen IDs are retained only for a short
    time‑to‑live and optionally capped by a maximum set size. Configure via:
      • ``DEDUP_TTL_SECONDS`` (default: 60)
      • ``DEDUP_MAX_ENTRIES`` (default: 10000)
    """

    def __init__(self, app):
        super().__init__(app)
        # TTL-bounded cache of request id -> first seen monotonic timestamp
        ttl_raw = float(os.getenv("DEDUP_TTL_SECONDS", "60"))
        max_raw = int(os.getenv("DEDUP_MAX_ENTRIES", "10000"))
        # Clamp to sane ranges to avoid misconfiguration foot-guns
        self._ttl: float = max(1.0, float(ttl_raw))
        self._max_entries: int = max(1, min(int(max_raw), 1_000_000))
        self._seen: TTLCache[str, float] = TTLCache(maxsize=self._max_entries, ttl=self._ttl)
        self._lock = asyncio.Lock()

    async def dispatch(self, request: Request, call_next):
        # Let CORS handle preflight; do NOTHING here for OPTIONS
        if request.method == "OPTIONS":
            # Important: do not create your own response; just pass through
            # CORS middleware will handle the preflight response
            return await call_next(request)
            
        now = time.monotonic()
        req_id = request.headers.get("X-Request-ID")
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
        response = await call_next(request)
        # Optionally update last seen time after completion
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
        req_id = incoming_id or (current_id if current_id and current_id != "-" else str(uuid.uuid4()))
        rec = LogRecord(req_id=req_id)
        token_req = req_id_var.set(req_id)
        token_rec = log_record_var.set(rec)
        
        # Set session/device ids if present
        rec.session_id = request.headers.get("X-Session-ID")
        rec.user_id = _anon_user_id(request)
        
        # Best-effort user accounting (do not affect request latency on failure)
        try:
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
                        _span.set_attribute("version", os.getenv("APP_VERSION") or os.getenv("GIT_TAG") or "")
                except Exception:
                    pass
                # Remove sensitive headers before passing to app log context
                try:
                    if "authorization" in request.headers:
                        request.headers.__dict__["_list"] = [
                            (k, v if k.decode().lower() != "authorization" else b"Bearer [REDACTED]")
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
                            _span.set_attribute("http.origin", request.headers.get("Origin", ""))
                            _span.set_attribute("http.status", status_code)
                            
                            # Set cookie flags for auth endpoints
                            if route_path == "/v1/auth/finish":
                                set_cookie_headers = response.headers.getlist("set-cookie", [])
                                cookie_flags = []
                                for cookie in set_cookie_headers:
                                    if "access_token" in cookie or "refresh_token" in cookie:
                                        flags = []
                                        if "HttpOnly" in cookie:
                                            flags.append("HttpOnly")
                                        if "Secure" in cookie:
                                            flags.append("Secure")
                                        if "SameSite=" in cookie:
                                            samesite = cookie.split("SameSite=")[1].split(";")[0]
                                            flags.append(f"SameSite={samesite}")
                                        cookie_flags.extend(flags)
                                if cookie_flags:
                                    _span.set_attribute("http.cookie_flags", " ".join(cookie_flags))
                except Exception:
                    pass
                    
                # Only stamp RL headers for non-OPTIONS requests
                # CORS preflight requests should never have rate limit headers
                if request.method != "OPTIONS":
                    try:
                        snap = get_rate_limit_snapshot(request)
                        if snap:
                            response.headers["ratelimit-limit"] = str(snap.get("limit"))
                            response.headers["ratelimit-remaining"] = str(snap.get("remaining"))
                            response.headers["ratelimit-reset"] = str(snap.get("reset"))
                            response.headers["X-RateLimit-Burst-Limit"] = str(snap.get("burst_limit"))
                            response.headers["X-RateLimit-Burst-Remaining"] = str(snap.get("burst_remaining"))
                            response.headers["X-RateLimit-Burst-Reset"] = str(snap.get("burst_reset"))
                    except Exception:
                        # Silently fail if rate limit snapshot fails
                        pass

            # Attach a compact logging meta for downstream log formatters and history
            # Include required fields: latency_ms, status_code, req_id, and router decision tag
            status_code = 0
            try:
                status_code = int(getattr(response, "status_code", 0)) if response is not None else 0
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
                    scopes = (raw_scopes.split() if isinstance(raw_scopes, str) else [str(s) for s in raw_scopes])
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
                "requests_remaining": (limit_bucket or {}).get("long_remaining") if isinstance(limit_bucket, dict) else None,
                "enforced_scope": " ".join(sorted(set(scopes))) if scopes else None,
                # Structured fields
                "user_id": getattr(request.state, "user_id", None) or rec.user_id,
                "route": route_path,
                "error_code": (getattr(getattr(response, "body_iterator", None), "status_code", None) or None),
            }
            
            try:
                # Skip logging for health check requests
                if route_path.startswith('/healthz') or route_path.startswith('/health/'):
                    pass
                else:
                    # log via std logging for live dashboards then persist in history
                    import logging, random as _rand
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
                        logging.getLogger(__name__).info("request_summary", extra={"meta": meta})
            except Exception:
                pass
                
            # Persist structured history (skip health checks)
            if not (route_path.startswith('/healthz') or route_path.startswith('/health/')):
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
                metrics.GESAHNI_REQUESTS_TOTAL.labels(route_path, request.method, str(status_code or 0)).inc()
            except Exception:
                pass
                
            # Observe with exemplar when possible to jump from Grafana to trace
            try:
                trace_id = get_trace_id_hex()
                hist = metrics.REQUEST_LATENCY.labels(route_path, request.method, engine)
                observe_with_exemplar(
                    hist,
                    rec.latency_ms / 1000,
                    exemplar_labels={"trace_id": trace_id} if trace_id else None,
                )
            except Exception:
                try:
                    metrics.REQUEST_LATENCY.labels(route_path, request.method, engine).observe(rec.latency_ms / 1000)
                except Exception:
                    pass
                    
            try:
                metrics.GESAHNI_LATENCY_SECONDS.labels(route_path).observe(rec.latency_ms / 1000)
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
                        response.headers.setdefault("Server-Timing", f"traceparent;desc={tid}")
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
                        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload")
                    # Security headers (CSP handled by frontend)
                    response.headers.setdefault("Referrer-Policy", "no-referrer")
                    response.headers.setdefault("X-Content-Type-Options", "nosniff")
                    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
                    response.headers.setdefault("X-Frame-Options", "DENY")
                except Exception:
                    pass
                    
                # Offline mode badge for UI: set a cookie when local fallback is in use
                try:
                    from .llama_integration import LLAMA_HEALTHY as _LL_OK
                    local_mode = (not _LL_OK) and (os.getenv("OPENAI_API_KEY", "") == "")
                    if local_mode:
                        # Enforce Secure/SameSite in prod; relax in tests/dev (http)
                        secure = True
                        try:
                            if getattr(request.url, "scheme", "http") != "https":
                                secure = False
                        except Exception:
                            pass
                        # Use centralized cookie functions for local mode indicator
                        from .cookies import set_named_cookie
                        set_named_cookie(
                            resp=response,
                            name="X-Local-Mode",
                            value="1",
                            ttl=600,
                            request=request,
                            httponly=True,
                            secure=secure,
                            samesite="Lax"  # Keep Lax for local mode indicator
                        )
                except Exception:
                    pass
                    
        except asyncio.TimeoutError:
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
    if os.getenv("DISABLE_SILENT_REFRESH", "0").strip().lower() in {"1", "true", "yes", "on"}:
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
            if path.endswith("/logout") or "/auth/logout" in path or request.headers.get("X-Logout") == "true":
                logger.debug("SILENT_REFRESH: Skipping logout path or X-Logout header")
                return response
            # Skip refresh if the response includes any Set-Cookie that deletes an auth cookie
            # (access_token, refresh_token, or __session)—i.e., a delete with Max-Age=0
            set_cookies = response.headers.getlist("set-cookie", [])
            auth_cookies = ["access_token", "refresh_token", "__session"]
            if any(any(cookie in h and "Max-Age=0" in h for cookie in auth_cookies) for h in set_cookies):
                logger.debug("SILENT_REFRESH: Skipping due to auth cookie deletion (Max-Age=0)")
                return response
            # Skip on 204 responses
            if response.status_code == 204:
                logger.debug("SILENT_REFRESH: Skipping due to 204 status code")
                return response
        except Exception:
            pass
        token = request.cookies.get("access_token")
        secret = os.getenv("JWT_SECRET")
        if not token or not secret:
            return response
        # Decode without hard-failing on expiry/format
        try:
            payload = jwt.decode(token, secret, algorithms=["HS256"])
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            payload = None
        except Exception:
            payload = None
        if not payload:
            return response
        now = int(time.time())
        exp = int(payload.get("exp", 0))
        threshold = int(os.getenv("ACCESS_REFRESH_THRESHOLD_SECONDS", "3600"))
        logger.debug("SILENT_REFRESH: Token expires in %s seconds, threshold is %s", exp - now, threshold)
        if exp - now <= threshold:
            logger.debug("SILENT_REFRESH: Token needs refresh, proceeding...")
            # Small jitter to avoid stampede when many tabs refresh concurrently
            try:
                import random as _rand
                import asyncio as _asyncio
                await _asyncio.sleep(_rand.uniform(0.01, 0.05))
            except Exception:
                pass
            # Rotate token, preserving custom claims
            user_id = str(payload.get("user_id") or "")
            if not user_id:
                return response
            # Use centralized TTL from tokens.py
            from .tokens import get_default_access_ttl
            lifetime = get_default_access_ttl()
            base_claims = {k: v for k, v in payload.items() if k not in {"iat", "exp", "nbf", "jti"}}
            base_claims["user_id"] = user_id
            # Use tokens.py facade instead of direct JWT encoding
            from .tokens import make_access
            new_token = make_access({"user_id": user_id}, ttl_s=lifetime)
            # Use centralized cookie configuration
            from .cookie_config import get_cookie_config, get_token_ttls
            
            cookie_config = get_cookie_config(request)
            access_ttl, _ = get_token_ttls()
            
            # Use centralized cookie functions for access token
            from .cookies import set_auth_cookies
            # For silent refresh, we only update the access token, keep existing refresh token
            # and don't set session cookie (it should already exist)
            set_auth_cookies(response, access=new_token, refresh="", session_id=None, access_ttl=access_ttl, refresh_ttl=0, request=request)
            # Optionally extend refresh cookie if present (best-effort) with jitter to avoid herd
            try:
                rtok = request.cookies.get("refresh_token")
                if rtok:
                    rp = jwt.decode(rtok, secret, algorithms=["HS256"])  # may raise
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
                            from .cookies import set_named_cookie
                            set_named_cookie(
                                resp=response,
                                name="refresh_token",
                                value=rtok,
                                ttl=r_life,
                                request=request,
                                httponly=cookie_config["httponly"]
                            )
                        except Exception:
                            # Fallback to centralized cookie functions
                            from .cookies import set_auth_cookies
                            # For refresh token extension, we need to set it individually
                            # since set_auth_cookies expects both access and refresh tokens
                            set_auth_cookies(
                                response, 
                                access="", 
                                refresh=rtok, 
                                session_id=None, 
                                access_ttl=0, 
                                refresh_ttl=r_life, 
                                request=request
                            )
            except Exception:
                pass
    except Exception:
        # best-effort; never fail request due to refresh
        pass
    return response

async def reload_env_middleware(request: Request, call_next):
    # Only reload env when explicitly enabled (e.g., in dev)
    try:
        if os.getenv("RELOAD_ENV_ON_REQUEST", os.getenv("ENV_RELOAD_ON_REQUEST", "0")).lower() in {"1", "true", "yes", "on"}:
            load_env()
    except Exception:
        pass
    return await call_next(request)

