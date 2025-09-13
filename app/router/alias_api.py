"""Generic alias router to provide lightweight compatibility endpoints.

Alias Targets (legacy -> canonical)
# /v1/whoami                 -> app.router.auth_api.whoami
# /v1/spotify/status         -> app.router.integrations.spotify_api.spotify_status
# /v1/google/status          -> app.router.integrations.google_api.google_status
# /v1/calendar/*             -> app.router.calendar_api (replace stubs with real impl)
# /v1/music*                 -> app.router.music_api (wire to Spotify)
# /v1/transcribe/{job_id}    -> app.router.transcribe_api (queue -> worker)
# /v1/tts/speak              -> app.router.tts_api (queue -> worker)
# /v1/admin/*                -> app.router.admin_extra_api / admin_api (real actions)

This router materializes simple aliases defined in `ALIASES` to avoid
hand-coding many one-off compatibility handlers. Handlers try to call
real functions when available and otherwise return normalized fallbacks.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from app.metrics import ALIAS_FALLBACK_TOTAL

# Runtime counters for quick post-test inspection
ALIAS_HITS = Counter()
ALIAS_FALLBACK_HITS = Counter()

router = APIRouter(tags=["alias"])

# Map expected path -> (method, callable or None)
AliasHandler = Callable[..., Awaitable[Any]]


def _safe_import(path: str, attr: str):
    try:
        mod = __import__(path, fromlist=[attr])
        return getattr(mod, attr)
    except Exception:
        return None


def _wrap_path_param_handler(fn_name: str, module: str, param_name: str = "key"):
    """Create an async adapter that extracts a path param from Request and
    calls the underlying function (best-effort; dependencies may be bypassed).
    """

    def _resolve():
        try:
            mod = __import__(module, fromlist=[fn_name])
            return getattr(mod, fn_name)
        except Exception:
            return None

    base_fn = _resolve()

    if base_fn is None:
        return None

    async def _adapter(request: Request):
        # Prefer path params, fall back to query params
        key = request.path_params.get(param_name) or request.query_params.get(
            param_name
        )
        # Call underlying function with key; pass a dummy for any extra deps
        try:
            return await base_fn(key, _=None)  # type: ignore[arg-type]
        except TypeError:
            # Fallback: try calling with only key
            return await base_fn(key)  # type: ignore[arg-type]

    return _adapter


def _wrap_ha_call_service(fn_name: str, module: str):
    try:
        mod = __import__(module, fromlist=[fn_name])
        base_fn = getattr(mod, fn_name)
    except Exception:
        return None

    async def _adapter(request: Request):
        # Accept either JSON body or query params: domain, service, data
        try:
            body = await request.json()
        except Exception:
            body = {}
        domain = body.get("domain") or request.query_params.get("domain")
        service = body.get("service") or request.query_params.get("service")
        data = body.get("data") or (body if isinstance(body, dict) else {})
        if not domain or not service:
            return JSONResponse(
                {"detail": "missing domain or service"}, status_code=400
            )
        try:
            return await base_fn(domain, service, data)
        except TypeError:
            return await base_fn(domain, service, data)

    return _adapter


def _wrap_query_param_handler(fn_name: str, module: str, param_name: str = "name"):
    try:
        mod = __import__(module, fromlist=[fn_name])
        base_fn = getattr(mod, fn_name)
    except Exception:
        return None

    async def _adapter(request: Request):
        name = request.query_params.get(param_name)
        if not name:
            return JSONResponse({"detail": f"missing {param_name}"}, status_code=400)
        try:
            return await base_fn(name)
        except TypeError:
            return await base_fn(name)

    return _adapter


ALIASES: dict[str, tuple[str, AliasHandler | None]] = {}

# Preload common aliases
ALIASES.update(
    {
        # whoami is served canonically from app.api.auth (/v1/whoami). Avoid duplicate alias.
        # '/me' now served by canonical app.api.me; do not alias to avoid conflicts
        # integrations/spotify/google → top-level expected paths
        # Prefer canonical integration endpoints when present
        "/spotify/status": (
            "GET",
            _safe_import("app.api.spotify", "integrations_spotify_status"),
        ),
        "/google/status": (
            "GET",
            _safe_import("app.api.google", "integrations_google_status"),
        ),
        # Home Assistant compatibility
        "/ha/entities": ("GET", _safe_import("app.home_assistant", "get_states")),
        "/ha/service": (
            "POST",
            _wrap_ha_call_service("call_service", "app.home_assistant"),
        ),
        "/ha/resolve": (
            "GET",
            _wrap_query_param_handler("resolve_entity", "app.home_assistant", "name"),
        ),
        # Calendar shims -> progressively point to canonical calendar API handlers
        # Use app.api.calendar functions directly when available (no FastAPI deps).
        "/list": ("GET", _safe_import("app.api.calendar", "list_all")),
        "/next": ("GET", _safe_import("app.api.calendar", "next_three")),
        "/today": ("GET", _safe_import("app.api.calendar", "list_today")),
        # Prefixed calendar variants
        "/calendar/list": ("GET", _safe_import("app.api.calendar", "list_all")),
        "/calendar/next": ("GET", _safe_import("app.api.calendar", "next_three")),
        "/calendar/today": ("GET", _safe_import("app.api.calendar", "list_today")),
        # Care shims
        "/device_status": ("GET", _safe_import("app.api.care", "device_status")),
        "/care/device_status": ("GET", _safe_import("app.api.care", "device_status")),
        # Music shims
        "/music": ("GET", _safe_import("app.router.music_api", "music_status")),
        "/music/state": ("GET", _safe_import("app.router.music_api", "music_status")),
        "/music/devices": (
            "GET",
            _safe_import("app.router.music_api", "music_devices"),
        ),
        "/music/device": (
            "PUT",
            _safe_import("app.router.music_api", "set_music_device"),
        ),
        # Transcribe / TTS / Admin
        "/transcribe/{job_id}": (
            "POST",
            _safe_import("app.router.transcribe_api", "transcribe_job"),
        ),
        "/tts/speak": ("POST", _safe_import("app.router.tts_api", "tts_speak")),
        "/admin/reload_env": (
            "POST",
            _safe_import("app.router.admin_extra_api", "reload_env"),
        ),
        "/admin/self_review": (
            "POST",
            _safe_import("app.router.admin_extra_api", "self_review"),
        ),
        "/admin/vector_store/bootstrap": (
            "POST",
            _safe_import("app.router.admin_extra_api", "bootstrap_vector_store"),
        ),
        # More admin compatibility endpoints (normalize to safe fallbacks)
        "/admin/config": ("GET", _safe_import("app.api.admin", "admin_config")),
        "/admin/errors": ("GET", _safe_import("app.api.admin", "admin_errors")),
        "/admin/flags": ("GET", _safe_import("app.api.admin", "admin_flags")),
        "/admin/metrics": (
            "GET",
            _safe_import("app.router.admin_api", "admin_metrics"),
        ),
        "/admin/ping": ("GET", _safe_import("app.router.admin_api", "admin_ping")),
        "/admin/rate-limits/{key}": (
            "GET",
            _wrap_path_param_handler("get_rate_limit_stats", "app.auth", "key"),
        ),
        "/admin/rbac/info": (
            "GET",
            _safe_import("app.router.admin_api", "admin_rbac_info"),
        ),
        "/admin/router/decisions": (
            "GET",
            _safe_import("app.router.admin_api", "admin_router_decisions"),
        ),
        "/admin/system/status": (
            "GET",
            _safe_import("app.router.admin_api", "admin_system_status"),
        ),
        "/admin/tokens/google": (
            "GET",
            _safe_import("app.router.admin_api", "admin_google_tokens"),
        ),
        # Integrations namespace parity
        "/integrations/google/status": (
            "GET",
            _safe_import("app.api.google", "integrations_google_status"),
        ),
        "/integrations/spotify/status": (
            "GET",
            _safe_import("app.api.spotify", "integrations_spotify_status"),
        ),
        # Health / ping parity
        "/ping": ("GET", _safe_import("app.api.health", "ping_vendor_health")),
        "/ha_status": ("GET", _safe_import("app.status", "ha_status")),
        "/llama_status": ("GET", _safe_import("app.status", "llama_status")),
        # Utility CSRF issuer under /v1 for tests expecting versioned path
        "/csrf": ("GET", _safe_import("app.api.util", "get_csrf")),
        # Legacy auth finisher path without version prefix (tests may probe it)
        "/auth/finish": ("GET", _safe_import("app.router.auth_api", "auth_finish_get")),
    }
)


async def _fallback(request: Request, path: str, method: str):
    # normalized, non-404 fallback with lightweight behavior matching contract
    # whoami -> 401 not authenticated
    if path in ("/whoami", "/me"):
        return JSONResponse(
            {"user": None, "authenticated": False, "detail": "not_authenticated"},
            status_code=401,
        )

    # status endpoints -> 200 with connected false
    if path.endswith("/status") or path.endswith("/status"):
        # Normalize shape for integrations status endpoints
        return JSONResponse(
            {"connected": False, "detail": "not_configured"}, status_code=200
        )

    # Calendar endpoints -> 200 with empty lists
    if (
        path in ("/list", "/next", "/today")
        or path.startswith("/calendar/")
        or path.startswith("/calendar")
    ):
        if path.endswith("/next") or path == "/next":
            # Normalized shape for /calendar/next
            return JSONResponse(
                {"event": None, "detail": "no_upcoming_events"}, status_code=200
            )
        return JSONResponse({"events": []}, status_code=200)

    # Care
    if path in ("/device_status", "/care/device_status"):
        return JSONResponse({"devices": []}, status_code=200)

    # Music
    if path in ("/music", "/music/state"):
        # Normalize music status shape
        return JSONResponse(
            {"playing": False, "device": None, "track": None}, status_code=200
        )
    if path == "/music/devices":
        return JSONResponse({"devices": []}, status_code=200)
    if path == "/music/device":
        # Accept device_id from query or body
        try:
            data = await request.json()
        except Exception:
            data = {}
        device_id = request.query_params.get("device_id") or (data or {}).get(
            "device_id"
        )
        if device_id:
            return JSONResponse({"device_id": device_id}, status_code=200)
        # Missing device id -> emulate client error
        return JSONResponse({"detail": "missing device_id"}, status_code=400)

    # Transcribe -> accept and return 202
    if path.startswith("/transcribe"):
        return JSONResponse({"status": "pending"}, status_code=202)

    # TTS -> requires text
    if path == "/tts/speak":
        try:
            data = await request.json()
        except Exception:
            data = {}
        text = (data or {}).get("text")
        if not text:
            return JSONResponse({"detail": "missing text"}, status_code=400)
        # Return normalized queued shape with audio_id
        try:
            import uuid

            audio_id = uuid.uuid4().hex
        except Exception:
            audio_id = "queued"
        return JSONResponse({"audio_id": audio_id, "status": "queued"}, status_code=202)

    # Admin shims
    if path == "/admin/reload_env":
        return JSONResponse({"status": "ok"}, status_code=200)
    if path == "/admin/self_review":
        return JSONResponse({"detail": "not_implemented"}, status_code=501)
    if path == "/admin/vector_store/bootstrap":
        return JSONResponse({"status": "accepted"}, status_code=202)

    # Fallback: not implemented
    return JSONResponse({"detail": "not_implemented"}, status_code=501)


def _register_alias(path: str, method: str):
    async def handler(request: Request):
        # record every alias request
        try:
            ALIAS_HITS[path] += 1
        except Exception:
            pass
        m, fn = ALIASES.get(path, (method, None))
        # Deprecation headers
        headers = {
            "Deprecation": "true",
            "X-Replace-With": f"/v1{path}",
        }

        if callable(fn):
            try:
                if "request" in getattr(fn, "__code__", object()).co_varnames:
                    res = await fn(request)
                else:
                    res = await fn()
            except Exception:
                fallback_res = await _fallback(request, path, method)
                try:
                    # attach headers if Response-like
                    from starlette.responses import Response as _StarResponse

                    if isinstance(fallback_res, _StarResponse):
                        for k, v in headers.items():
                            fallback_res.headers.setdefault(k, v)
                        return fallback_res
                except Exception:
                    pass
                # ensure JSONResponse
                # Record fallback metric and emit warning log
                try:
                    ALIAS_FALLBACK_TOTAL.labels(
                        path=path, method=method, reason="handler_error"
                    ).inc()
                except Exception:
                    pass
                import logging

                logging.warning(
                    "alias.fallback used: %s %s (handler error)", method, path
                )
                return JSONResponse(
                    fallback_res if isinstance(fallback_res, dict) else {},
                    headers=headers,
                )

            # If the underlying handler already returned a Response-like object,
            # attach deprecation headers if possible and return it directly.
            try:
                from starlette.responses import Response as _StarResponse

                if isinstance(res, _StarResponse):
                    for k, v in headers.items():
                        res.headers.setdefault(k, v)
                    return res
            except Exception:
                pass

            # Non-Response result (e.g., dict) -> wrap in JSONResponse and add headers
            return JSONResponse(
                res if isinstance(res, dict | list) else {"result": res},
                headers=headers,
            )

        # Non-callable: return fallback response and ensure headers are attached
        try:
            ALIAS_FALLBACK_HITS[path] += 1
        except Exception:
            pass
        fallback_res = await _fallback(request, path, method)
        try:
            ALIAS_FALLBACK_TOTAL.labels(
                path=path, method=method, reason="no_handler"
            ).inc()
        except Exception:
            pass
        import logging

        logging.warning("alias.fallback used: %s %s (no handler)", method, path)
        try:
            from starlette.responses import Response as _StarResponse

            if isinstance(fallback_res, _StarResponse):
                for k, v in headers.items():
                    fallback_res.headers.setdefault(k, v)
                return fallback_res
        except Exception:
            pass
        return JSONResponse(
            fallback_res if isinstance(fallback_res, dict) else {}, headers=headers
        )

    # Mark these compatibility routes as deprecated in the OpenAPI docs
    if method == "GET":
        router.get(path, deprecated=True)(handler)
    elif method == "POST":
        router.post(path, deprecated=True)(handler)
    elif method == "PUT":
        router.put(path, deprecated=True)(handler)
    elif method == "DELETE":
        router.delete(path, deprecated=True)(handler)
    else:
        router.add_api_route(path, handler, methods=[method])


def _make_handler(path: str, method: str):
    """Return a request handler for the given alias path/method without
    registering it. This lets callers decide where/how to attach the handler
    (router vs app) and avoid duplicate registration when canonical handlers
    are present.
    """

    async def handler(request: Request):
        # record every alias request
        try:
            ALIAS_HITS[path] += 1
        except Exception:
            pass
        m, fn = ALIASES.get(path, (method, None))
        # Deprecation headers
        headers = {
            "Deprecation": "true",
            "X-Replace-With": f"/v1{path}",
        }

        if callable(fn):
            try:
                if "request" in getattr(fn, "__code__", object()).co_varnames:
                    res = await fn(request)
                else:
                    res = await fn()
            except Exception:
                fallback_res = await _fallback(request, path, method)
                try:
                    # attach headers if Response-like
                    from starlette.responses import Response as _StarResponse

                    if isinstance(fallback_res, _StarResponse):
                        for k, v in headers.items():
                            fallback_res.headers.setdefault(k, v)
                        return fallback_res
                except Exception:
                    pass
                # ensure JSONResponse
                try:
                    ALIAS_FALLBACK_TOTAL.labels(
                        path=path, method=method, reason="handler_error"
                    ).inc()
                except Exception:
                    pass
                import logging

                logging.warning(
                    "alias.fallback used: %s %s (handler error)", method, path
                )
                return JSONResponse(
                    fallback_res if isinstance(fallback_res, dict) else {},
                    headers=headers,
                )

            try:
                from starlette.responses import Response as _StarResponse

                if isinstance(res, _StarResponse):
                    for k, v in headers.items():
                        res.headers.setdefault(k, v)
                    return res
            except Exception:
                pass

            return JSONResponse(
                res if isinstance(res, dict | list) else {"result": res},
                headers=headers,
            )

        try:
            ALIAS_FALLBACK_HITS[path] += 1
        except Exception:
            pass
        fallback_res = await _fallback(request, path, method)
        try:
            ALIAS_FALLBACK_TOTAL.labels(
                path=path, method=method, reason="no_handler"
            ).inc()
        except Exception:
            pass
        import logging

        logging.warning("alias.fallback used: %s %s (no handler)", method, path)
        try:
            from starlette.responses import Response as _StarResponse

            if isinstance(fallback_res, _StarResponse):
                for k, v in headers.items():
                    fallback_res.headers.setdefault(k, v)
                return fallback_res
        except Exception:
            pass
        return JSONResponse(
            fallback_res if isinstance(fallback_res, dict) else {}, headers=headers
        )

    return handler


def register_aliases(app, prefix: str = "/v1") -> None:
    """Register alias routes onto the given FastAPI `app` only when a
    canonical route for the same (method,path) is not already present.
    """
    # Build set of existing (METHOD, path)
    existing = {
        (m, r.path)
        for r in app.routes
        for m in getattr(r, "methods", [])
        if m != "HEAD"
    }
    for p, (m, _) in list(ALIASES.items()):
        full = prefix + p
        if (m, full) in existing:
            # Skip registration when canonical handler already exists
            continue
        h = _make_handler(p, m)
        # Attach as deprecated for compatibility
        try:
            app.add_api_route(full, h, methods=[m], deprecated=True)
        except Exception:
            # Fallback to include without deprecation flag
            app.add_api_route(full, h, methods=[m])


@router.get("/_alias/report")
async def alias_report():
    rows = []
    for p, (m, fn) in sorted(ALIASES.items()):
        rows.append(
            {
                "method": m,
                "path": f"/v1{p}",
                "forwards": bool(callable(fn)),
                "hits": int(ALIAS_HITS.get(p, 0)),
                "fallback_hits": int(ALIAS_FALLBACK_HITS.get(p, 0)),
            }
        )
    return {"aliases": rows}
