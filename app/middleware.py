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

from .logging_config import req_id_var
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


async def trace_request(request: Request, call_next):
    # Unify request id across middlewares and response
    incoming_id = request.headers.get("X-Request-ID")
    current_id = req_id_var.get()
    req_id = incoming_id or (current_id if current_id and current_id != "-" else str(uuid.uuid4()))
    rec = LogRecord(req_id=req_id)
    token_req = req_id_var.set(req_id)
    token_rec = log_record_var.set(rec)
    # Redact tokens from logs
    def _redact(s: str | None) -> str | None:
        if not s:
            return s
        if "Bearer " in s:
            return "Bearer [REDACTED]"
        return s
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
                # Avoid logging query strings
                "http.target": safe_target,
                "user.anonymous_id": rec.user_id,
            },
        ) as _span:
            # Remove sensitive headers before passing to app log context
            try:
                if "authorization" in request.headers:
                    request.headers.__dict__["_list"] = [
                        (k, v if k.decode().lower() != "authorization" else b"Bearer [REDACTED]")
                        for (k, v) in request.headers.raw
                    ]
            except Exception:
                pass
            # Skip CORS preflight requests from consuming downstream budget and heavy work
            if str(request.method).upper() == "OPTIONS":
                return Response(status_code=204)
            response = await call_next(request)
            rec.status = "OK"
            try:
                if _span is not None and hasattr(_span, "set_attribute"):
                    _span.set_attribute("http.status_code", getattr(response, "status_code", 200))
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
        rec.latency_ms = int((time.monotonic() - start_time) * 1000)
        # Keep this synchronous so tests and dashboards see updated p95 immediately
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
                # Nonce-based CSP and allow WS/connect only to our host
                try:
                    import secrets as _secrets
                    csp_nonce = _secrets.token_urlsafe(16)
                except Exception:
                    csp_nonce = None
                try:
                    host = request.url.hostname or "localhost"
                    port = request.url.port
                    hostport = f"{host}:{port}" if port else host
                    ws_scheme = "wss" if request.url.scheme == "https" else "ws"
                    ws_origin = f"{ws_scheme}://{hostport}"
                    https_origin = f"https://{hostport}"
                except Exception:
                    ws_origin = "wss://localhost"
                    https_origin = "https://localhost"
                script_src = f"'self' 'nonce-{csp_nonce}'" if csp_nonce else "'self'"
                style_src = f"'self' 'nonce-{csp_nonce}'" if csp_nonce else "'self'"
                # Allow local FastAPI (http) and WS in dev via Next.js proxy
                csp = (
                    "default-src 'self'; "
                    + "img-src 'self' data:; "
                    + f"style-src {style_src}; "
                    + f"script-src {script_src}; "
                    + f"connect-src 'self' http://localhost:8000 {https_origin} {ws_origin} ws://localhost:8000; "
                    + "font-src 'self' data:; frame-ancestors 'none'"
                )
                response.headers.setdefault("Content-Security-Policy", csp)
                if csp_nonce:
                    response.headers.setdefault("X-CSP-Nonce", str(csp_nonce))
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
                    response.set_cookie(
                        "X-Local-Mode",
                        "1",
                        max_age=600,
                        path="/",
                        secure=secure,
                        httponly=True,
                        samesite="Lax",
                    )
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
        # Persist structured history
        full = {**rec.model_dump(exclude_none=True), **{"meta": meta}}
        try:
            asyncio.create_task(append_history(full))
        except Exception:
            pass
        # Also store a compact decision record for admin UI and explain endpoint
        try:
            asyncio.create_task(asyncio.to_thread(add_decision, full))
        except Exception:
            pass
        # Ensure at least a minimal trace exists
        try:
            asyncio.create_task(asyncio.to_thread(add_trace_event, rec.req_id, "request_end", status=rec.status, latency_ms=rec.latency_ms))
        except Exception:
            pass
        log_record_var.reset(token_rec)
        req_id_var.reset(token_req)
    return response


async def silent_refresh_middleware(request: Request, call_next):
    """Rotate access and refresh cookies server-side when nearing expiry.

    Controlled via env:
      - JWT_SECRET: required to decode/encode
      - JWT_ACCESS_TTL_SECONDS: lifetime of new tokens (default 14d)
      - ACCESS_REFRESH_THRESHOLD_SECONDS: refresh when exp - now < threshold (default 3600s)
    """
    # Call downstream first; do not swallow exceptions from handlers
    response: Response = await call_next(request)

    # Best-effort refresh; never raise from middleware
    try:
        # Skip static and non-API paths to avoid unnecessary token work
        try:
            path = request.url.path or ""
            if not path.startswith("/v1"):
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
        if exp - now <= threshold:
            # Small jitter to avoid stampede when many tabs refresh concurrently
            try:
                import random as _rand
                import asyncio as _asyncio
                await _asyncio.sleep(_rand.uniform(0.05, 0.25))
            except Exception:
                pass
            # Rotate token, preserving custom claims
            user_id = str(payload.get("user_id") or "")
            if not user_id:
                return response
            lifetime = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "1209600"))
            base_claims = {k: v for k, v in payload.items() if k not in {"iat", "exp", "nbf", "jti"}}
            base_claims["user_id"] = user_id
            new_payload = {**base_claims, "iat": now, "exp": now + lifetime}
            new_token = jwt.encode(new_payload, secret, algorithm="HS256")
            # Canonicalize SameSite and decide Secure based on scheme
            raw_secure = os.getenv("COOKIE_SECURE", "1").lower() in {"1", "true", "yes"}
            raw_samesite = os.getenv("COOKIE_SAMESITE", "lax").lower()
            samesite_map = {"lax": "Lax", "strict": "Strict", "none": "None"}
            cookie_samesite = samesite_map.get(raw_samesite, "Lax")
            cookie_secure = True if cookie_samesite == "None" else raw_secure
            # In dev over http, prefer not Secure unless SameSite=None is explicitly requested
            try:
                if getattr(request.url, "scheme", "http") != "https" and cookie_samesite != "None":
                    cookie_secure = False
            except Exception:
                pass
            try:
                from .api.auth import _append_cookie_with_priority as _append
                _append(response, key="access_token", value=new_token, max_age=lifetime, secure=cookie_secure, samesite=cookie_samesite)
            except Exception:
                response.set_cookie(
                    key="access_token",
                    value=new_token,
                    httponly=True,
                    secure=cookie_secure,
                    samesite=cookie_samesite,
                    max_age=lifetime,
                    path="/",
                )
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
                            await asyncio.sleep(_rand.uniform(0.05, 0.25))  # type: ignore[name-defined]
                        except Exception:
                            pass
                        try:
                            from .api.auth import _append_cookie_with_priority as _append
                            _append(response, key="refresh_token", value=rtok, max_age=r_life, secure=cookie_secure, samesite=cookie_samesite)
                        except Exception:
                            response.set_cookie(
                                key="refresh_token",
                                value=rtok,
                                httponly=True,
                                secure=cookie_secure,
                                samesite=cookie_samesite,
                                max_age=r_life,
                                path="/",
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
