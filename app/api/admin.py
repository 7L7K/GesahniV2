from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request
import logging
from fastapi.responses import StreamingResponse
import asyncio
import json
from pydantic import BaseModel, ConfigDict

from app.deps.user import get_current_user_id
from app.deps.scopes import optional_require_any_scope
from app.deps.roles import require_roles
from app.security import verify_token
from app.status import _admin_token
from app.analytics import (
    get_metrics,
    cache_hit_rate,
    get_top_skills,
    latency_p95,
)
from app.decisions import get_recent as decisions_recent, get_explain as decisions_get
from app.config_runtime import get_config
from app.feature_flags import list_flags as _list_flags, set_value as _set_flag
from app.models.tv import TvConfig, TvConfigResponse, QuietHours, TVConfigUpdate
from app.jobs.qdrant_lifecycle import bootstrap_collection as _q_bootstrap, collection_stats as _q_stats
from app.jobs.migrate_chroma_to_qdrant import main as _migrate_cli  # type: ignore
from app.logging_config import get_last_errors
try:
    from app.proactive_engine import get_self_review as _get_self_review  # type: ignore
except Exception:  # pragma: no cover - optional
    def _get_self_review():  # type: ignore
        return None
try:
    from app.admin.routes import router as admin_inspect_router
except Exception:
    admin_inspect_router = None  # type: ignore

router = APIRouter(tags=["Admin"], dependencies=[Depends(verify_token), Depends(require_roles(["admin"]))])
logger = logging.getLogger(__name__)


def _is_test_mode() -> bool:
    """Return True when running under tests.

    Accept multiple hints so isolated tests don't have to coordinate env vars.
    """
    v = lambda s: str(os.getenv(s, "")).strip().lower()
    return (
        v("PYTEST_MODE") in {"1", "true", "yes", "on"}
        or v("PYTEST_RUNNING") in {"1", "true", "yes"}
        or v("ENV") == "test"
    )


def _check_admin(token: str | None, request: Request | None = None) -> None:
    """Enforce admin token when configured.

    In test runs (PYTEST_RUNNING=1), allow access when no token query param
    is supplied so unit tests can read config without coupling to env.
    When a token is explicitly provided, still enforce matching behavior.
    """
    _tok = _admin_token()
    # In production-like runs, require ADMIN_TOKEN to be set
    if not _is_test_mode() and not _tok:
        raise HTTPException(status_code=403, detail="admin_token_required")
    # Extract from headers or cookies if not provided as query
    header_token: str | None = None
    cookie_token: str | None = None
    if request is not None:
        try:
            auth = request.headers.get("Authorization") or ""
            if auth.startswith("Bearer "):
                header_token = auth.split(" ", 1)[1]
            header_token = header_token or request.headers.get("X-Admin-Token")
            cookie_token = request.cookies.get("admin_token")
        except Exception:
            pass
    candidate = token or header_token or cookie_token
    # In tests, allow access when token is omitted entirely
    if _is_test_mode() and candidate is None:
        return
    if _tok and candidate != _tok:
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/admin/surface/index")
async def admin_surface_index(
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    """Return a generated index of HTTP (OpenAPI) and WS routes to prevent drift."""
    _check_admin(token, request)
    try:
        from app.main import app as _app  # type: ignore
        schema = _app.openapi()
        ws_list: list[dict] = []
        try:
            from fastapi.routing import WebSocketRoute  # type: ignore
            for r in _app.routes:
                try:
                    if isinstance(r, WebSocketRoute):
                        ws_list.append({
                            "path": getattr(r, "path", None),
                            "name": getattr(r, "name", None),
                            "endpoint": getattr(getattr(r, "endpoint", None), "__name__", None),
                        })
                    sub = getattr(r, "routes", None)
                    if sub:
                        for rr in sub:
                            if isinstance(rr, WebSocketRoute):
                                ws_list.append({
                                    "path": getattr(rr, "path", None),
                                    "name": getattr(rr, "name", None),
                                    "endpoint": getattr(getattr(rr, "endpoint", None), "__name__", None),
                                })
                except Exception:
                    continue
        except Exception:
            ws_list = []
        return {"openapi": schema, "websockets": ws_list}
    except Exception as e:
        logger.exception("admin.surface_index error: %s", e)
        raise HTTPException(status_code=500, detail="surface_index_error")


@router.get("/admin/metrics")
async def admin_metrics(
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    _check_admin(token, request)
    m = get_metrics()
    # Derived fields that are useful in dashboards
    transcribe_count = max(0, int(m.get("transcribe_count", 0)))
    transcribe_errors = max(0, int(m.get("transcribe_errors", 0)))
    transcribe_error_rate = (
        round(100.0 * transcribe_errors / transcribe_count, 2) if transcribe_count else 0.0
    )
    out = {
        "metrics": m,
        "cache_hit_rate": cache_hit_rate(),
        "latency_p95_ms": latency_p95(),
        "transcribe_error_rate": transcribe_error_rate,
        "top_skills": get_top_skills(10),
    }
    return out


@router.get("/admin/router/decisions")
async def admin_router_decisions(
    limit: int = Query(default=500, ge=1, le=1000),
    cursor: int = Query(default=0, ge=0),
    engine: str | None = Query(default=None, description="Filter by engine (gpt|llama|...)"),
    model: str | None = Query(default=None, description="Filter by model name contains"),
    cache_hit: bool | None = Query(default=None),
    escalated: bool | None = Query(default=None),
    intent: str | None = Query(default=None),
    q: str | None = Query(default=None, description="Substring match in route_reason"),
    since: str | None = Query(default=None, description="ISO timestamp lower bound (inclusive)"),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    from datetime import datetime
    _check_admin(token, request)
    _raw = decisions_recent(1000)
    items = _raw if isinstance(_raw, list) else []
    # Apply filters
    if engine:
        items = [it for it in items if (it.get("engine") or "").lower() == engine.lower()]
    if model:
        s = model.lower()
        items = [it for it in items if s in (it.get("model") or "").lower()]
    if cache_hit is not None:
        items = [it for it in items if bool(it.get("cache_hit")) == cache_hit]
    if escalated is not None:
        items = [it for it in items if bool(it.get("escalated")) == escalated]
    if intent:
        s = intent.lower()
        items = [it for it in items if s in (it.get("intent") or "").lower()]
    if q:
        s = q.lower()
        items = [it for it in items if s in (it.get("route_reason") or "").lower()]
    if since:
        try:
            t0 = datetime.fromisoformat(since)
            def _parse(ts: str | None):
                try:
                    return datetime.fromisoformat(ts) if ts else None
                except Exception:
                    return None
            items = [it for it in items if (_parse(it.get("timestamp")) or t0) >= t0]
        except Exception:
            # ignore bad since parameter
            pass
    total = len(items)
    sliced = items[cursor: cursor + limit]
    next_cursor = cursor + len(sliced) if (cursor + len(sliced)) < total else None
    return {"items": sliced, "total": total, "next_cursor": next_cursor}


@router.get("/admin/router/decisions.ndjson")
async def admin_router_decisions_ndjson(
    limit: int = Query(default=500, ge=1, le=1000),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    """Download last N router decisions as NDJSON (for audit pipelines)."""
    _check_admin(token, request)
    _raw = decisions_recent(limit)
    items = _raw if isinstance(_raw, list) else []

    def _iter():
        for it in items:
            try:
                yield json.dumps(it, ensure_ascii=False) + "\n"
            except Exception:
                # best-effort; skip malformed entries
                continue

    return StreamingResponse(_iter(), media_type="application/x-ndjson")


@router.get("/admin/retrieval/last")
async def admin_retrieval_last(
    limit: int = Query(default=200, ge=1, le=2000),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    """Return last N retrieval traces (subset of router decisions), most recent first."""
    _check_admin(token, request)
    _raw = decisions_recent(limit)
    items = _raw if isinstance(_raw, list) else []
    # filter to those that have a retrieval_trace event
    out = []
    for it in items:
        trace = it.get("trace") or []
        if any(ev.get("event") == "retrieval_trace" for ev in trace):
            out.append(it)
    return {"items": out[:limit]}


@router.get("/admin/diagnostics/requests")
async def admin_diagnostics_requests(
    limit: int = Query(default=50, ge=1, le=200),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    """Return last N request IDs with timestamps for quick diagnostics."""
    _check_admin(token, request)
    _raw = decisions_recent(limit)
    items = _raw if isinstance(_raw, list) else []
    out = [
        {"req_id": it.get("req_id"), "timestamp": it.get("timestamp")}
        for it in items
        if it.get("req_id")
    ]
    return {"items": out}


@router.get("/admin/decisions/explain")
async def explain_decision(
    req_id: str,
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token, request)
    data = decisions_get(req_id)
    if not data:
        raise HTTPException(status_code=404, detail="not_found")
    return data


@router.get("/admin/config", dependencies=[Depends(verify_token), Depends(optional_require_any_scope(["admin", "admin:write"]))])
async def admin_config(
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token, request)
    data = get_config().to_dict()
    # Overlay a few live values for observability at runtime
    import os as _os
    data["store"]["vector_store"] = (_os.getenv("VECTOR_STORE") or data["store"]["vector_store"]).lower()
    data["store"]["qdrant_collection"] = _os.getenv("QDRANT_COLLECTION", data["store"].get("qdrant_collection", "kb:default"))
    data["store"]["active_collection"] = data["store"]["qdrant_collection"]
    return data


class AdminOkResponse(BaseModel):
    status: str = "ok"

    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})


@router.post(
    "/admin/reload_env",
    
    
    response_model=AdminOkResponse,
    responses={200: {"model": AdminOkResponse}},
    openapi_extra={
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"example": {}}
                }
            }
        }
    },
)
async def admin_reload_env(
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token, request)
    try:
        from app.env_utils import load_env
        logger.info("admin.reload_env", extra={"meta": {"user": user_id}})
        load_env()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/errors")
async def admin_errors(
    limit: int = Query(default=50, ge=1, le=500),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    _check_admin(token, request)
    return {"errors": get_last_errors(limit)}


@router.get("/admin/self_review")
async def admin_self_review(
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
) -> dict:
    _check_admin(token, request)
    try:
        res = _get_self_review()
        return res or {"status": "unavailable"}
    except Exception:
        return {"status": "unavailable"}


class AdminBootstrapResponse(BaseModel):
    status: str
    collection: str
    existed: str

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"status": "ok", "collection": "kb:default", "existed": "False"}
        }
    )


@router.post("/admin/vector_store/bootstrap", response_model=AdminBootstrapResponse, responses={200: {"model": AdminBootstrapResponse}})
async def admin_vs_bootstrap(
    name: str | None = Query(default=None),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token, request)
    logger.info("admin.vector_bootstrap", extra={"meta": {"user": user_id, "collection": name or (os.getenv("QDRANT_COLLECTION") or "kb:default")}})
    coll = name or (os.getenv("QDRANT_COLLECTION") or "kb:default")
    try:
        res = _q_bootstrap(coll, int(os.getenv("EMBED_DIM", "1536")))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return res
class AdminStartedResponse(BaseModel):
    status: str
    action: str
    dry_run: bool
    out_dir: str | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "started",
                "action": "migrate",
                "dry_run": True,
                "out_dir": "/tmp/out",
            }
        }
    )


@router.post("/admin/vector_store/migrate", response_model=AdminStartedResponse, responses={200: {"model": AdminStartedResponse}})
async def admin_vs_migrate(
    action: str = Query(default="migrate", pattern="^(inventory|export|migrate)$"),
    dry_run: bool = Query(default=True),
    out_dir: str | None = Query(default=None),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token, request)
    logger.info("admin.vector_migrate", extra={"meta": {"user": user_id, "action": action, "dry_run": dry_run, "out_dir": out_dir}})
    argv = [action]
    if dry_run:
        argv.append("--dry-run")
    if out_dir:
        argv.extend(["--out-dir", out_dir])
    try:
        _migrate_cli(argv)
    except SystemExit:
        # argparse exits; swallow for HTTP context
        pass
    return {"status": "started", "action": action, "dry_run": dry_run, "out_dir": out_dir}


def _sse_format(event: str | None, data: dict | str | None) -> str:
    payload = data if isinstance(data, str) else json.dumps(data or {})
    if event:
        return f"event: {event}\n" + f"data: {payload}\n\n"
    return f"data: {payload}\n\n"


@router.get("/admin/vector_store/bootstrap/stream")
async def admin_vs_bootstrap_stream(
    name: str | None = Query(default=None),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    """SSE stream for Qdrant bootstrap with idempotence.

    Emits events: start, step, done, error.
    """
    _check_admin(token, request)
    logger.info("admin.vector_bootstrap_stream", extra={"meta": {"user": user_id, "collection": coll}})
    coll = name or (os.getenv("QDRANT_COLLECTION") or "kb:default")

    async def _agen():
        yield _sse_format("start", {"collection": coll})
        try:
            yield _sse_format("step", {"msg": f"Ensuring collection {coll}"})
            res = _q_bootstrap(coll, int(os.getenv("EMBED_DIM", "1536")))
            yield _sse_format("step", {"result": res})
            yield _sse_format("done", {"status": "ok", "idempotent": True})
        except Exception as e:
            yield _sse_format("error", {"error": str(e)})

    return StreamingResponse(_agen(), media_type="text/event-stream")


@router.get("/admin/vector_store/migrate/stream")
async def admin_vs_migrate_stream(
    action: str = Query(default="migrate", pattern="^(inventory|export|migrate)$"),
    dry_run: bool = Query(default=True),
    out_dir: str | None = Query(default=None),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    """SSE stream for Chroma → Qdrant migration with idempotence.

    Uses in-process calls for portability; degrades gracefully when deps missing.
    """
    _check_admin(token, request)
    logger.info("admin.vector_migrate_stream", extra={"meta": {"user": user_id, "action": action, "dry_run": dry_run, "out_dir": out_dir}})

    async def _agen():
        yield _sse_format("start", {"action": action, "dry_run": dry_run, "out_dir": out_dir})
        try:
            # Import lazily to avoid heavy deps on startup
            import importlib

            mod = importlib.import_module("app.jobs.migrate_chroma_to_qdrant")

            if action == "inventory":
                inv = mod._inventory_chroma()  # type: ignore[attr-defined]
                yield _sse_format("step", {"inventory": inv})
                yield _sse_format("done", {"status": "ok"})
                return

            cli = mod._open_chroma()  # type: ignore[attr-defined]
            qc = mod._open_qdrant()  # type: ignore[attr-defined]

            if action == "export":
                qa = mod._export_qa(cli)  # type: ignore[attr-defined]
                um = mod._export_user_memories(cli)  # type: ignore[attr-defined]
                yield _sse_format("step", {"qa_cache": len(qa), "user_memories": len(um)})
                if out_dir:
                    mod._write_jsonl(os.path.join(out_dir, "qa_cache.jsonl"), [  # type: ignore[attr-defined]
                        {"id": i, "document": d, "metadata": m} for (i, d, m) in qa
                    ])
                    mod._write_jsonl(os.path.join(out_dir, "user_memories.jsonl"), [  # type: ignore[attr-defined]
                        {"id": i, "text": d, "metadata": m} for (i, d, m) in um
                    ])
                    yield _sse_format("step", {"exported_to": out_dir})
                yield _sse_format("done", {"status": "ok"})
                return

            # migrate
            qa = mod._export_qa(cli)  # type: ignore[attr-defined]
            um = mod._export_user_memories(cli)  # type: ignore[attr-defined]
            yield _sse_format("step", {"phase": "export", "qa_cache": len(qa), "user_memories": len(um)})
            moved_qa = mod._upsert_qa(qc, qa, dry_run=dry_run)  # type: ignore[attr-defined]
            yield _sse_format("step", {"phase": "upsert_qa", "count": moved_qa, "idempotent": True})
            moved_um = mod._upsert_user_memories(qc, um, dry_run=dry_run)  # type: ignore[attr-defined]
            yield _sse_format("step", {"phase": "upsert_user_memories", "count": moved_um, "idempotent": True})
            yield _sse_format("done", {"status": "ok", "dry_run": dry_run})
        except Exception as e:
            yield _sse_format("error", {"error": str(e)})

    return StreamingResponse(_agen(), media_type="text/event-stream")



@router.get("/admin/vector_store/stats")
async def admin_vs_stats(
    name: str | None = Query(default=None),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token, request)
    coll = name or (os.getenv("QDRANT_COLLECTION") or "kb:default")
    try:
        return _q_stats(coll)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/qdrant/collections")
async def admin_qdrant_collections(
    names: str | None = Query(default=None, description="CSV of collection names"),
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token, request)
    cols = [c.strip() for c in (names.split(",") if names else []) if c.strip()]
    if not cols:
        # fall back to default only
        cols = [os.getenv("QDRANT_COLLECTION", "kb:default")]
    out = {}
    for c in cols:
        try:
            out[c] = _q_stats(c)
        except Exception as e:
            out[c] = {"error": str(e)}
    return {"collections": out}


class AdminFlagsResponse(BaseModel):
    status: str = "ok"
    key: str
    value: str
    flags: dict

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "key": "RETRIEVAL_PIPELINE",
                "value": "dual",
                "flags": {"RETRIEVAL_PIPELINE": "dual"},
            }
        }
    )


class AdminFlagBody(BaseModel):
    key: str
    value: str

    model_config = ConfigDict(title="AdminFlagBody", json_schema_extra={"example": {"key": "RETRIEVAL_PIPELINE", "value": "dual"}})


@router.post(
    "/admin/flags",
    response_model=AdminFlagsResponse,
    responses={200: {"model": AdminFlagsResponse}},
    openapi_extra={
        "requestBody": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/AdminFlagBody"}}}}
    },
)
async def admin_flags(
    token: str | None = Query(default=None),
    request: Request = None,
    body: AdminFlagBody | None = None,
    key: str | None = Query(default=None),
    value: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    """Flip runtime flags (process env) — best-effort.

    Guarded by admin token. Note: only affects this process; not persisted.
    """
    # Enforce admin guard before reading/validating request body
    _check_admin(token, request)

    # Normalize inputs: prefer JSON body when provided; otherwise use query params
    if body is not None:
        key = key or body.key
        value = value or body.value

    if not key:
        raise HTTPException(status_code=400, detail="missing_key")
    if value is None or value == "":
        raise HTTPException(status_code=400, detail="missing_value")
    logger.info("admin.flags.set", extra={"meta": {"user": user_id, "key": key, "value": value}})
    _set_flag(key, value)
    os.environ[f"FLAG_{key.upper()}"] = value
    # Maintain backward-compat: also set plain key for legacy tests/tools
    os.environ[key] = value
    return {"status": "ok", "key": key, "value": value, "flags": _list_flags()}


@router.get("/admin/health/router_retrieval")
async def admin_health_router_retrieval(
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    """Snapshot of router + retrieval config with basic validation and telemetry hints."""
    _check_admin(token, request)
    out: dict = {"router": {}, "retrieval": {}, "warnings": []}
    try:
        import app.model_router as mr  # type: ignore
        try:
            rules = mr._load_rules()  # type: ignore[attr-defined]
        except Exception:
            rules = None
        out["router"] = {
            "rules_loaded": bool(rules),
            "rule_values": rules or {
                "MAX_SHORT_PROMPT_TOKENS": mr.MAX_SHORT_PROMPT_TOKENS,
                "RAG_LONG_CONTEXT_THRESHOLD": mr.RAG_LONG_CONTEXT_THRESHOLD,
                "DOC_LONG_REPLY_TARGET": mr.DOC_LONG_REPLY_TARGET,
                "OPS_MAX_FILES_SIMPLE": mr.OPS_MAX_FILES_SIMPLE,
                "SELF_CHECK_FAIL_THRESHOLD": mr.SELF_CHECK_FAIL_THRESHOLD,
                "MAX_RETRIES_PER_REQUEST": mr.MAX_RETRIES_PER_REQUEST,
            },
        }
    except Exception as e:
        out["warnings"].append(f"router_rules_error: {e}")
    try:
        from app.config_runtime import get_config as _get_cfg  # type: ignore
        cfg = _get_cfg()
        import os as _os
        th_raw = _os.getenv("RETRIEVE_DENSE_SIM_THRESHOLD", "0.75")
        try:
            th = float(th_raw)
        except Exception:
            th = None
        out["retrieval"] = {
            "use_pipeline": _os.getenv("USE_RETRIEVAL_PIPELINE", "0").lower() in {"1", "true", "yes"},
            "dense_sim_threshold": th,
            "mmr_lambda": getattr(cfg.retrieval, "mmr_lambda", None),
            "topk_vec": getattr(cfg.retrieval, "topk_vec", None),
            "topk_final": getattr(cfg.retrieval, "topk_final", None),
        }
        if th is None or not (0.0 <= th <= 1.0):
            out["warnings"].append(f"threshold_invalid: RETRIEVE_DENSE_SIM_THRESHOLD={th_raw}")
    except Exception as e:
        out["warnings"].append(f"retrieval_cfg_error: {e}")
    return out


@router.get("/admin/flags")
async def admin_list_flags(
    token: str | None = Query(default=None),
    request: Request = None,
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token, request)
    return {"flags": _list_flags()}


# Mount new admin-inspect routes under the same router if available
if admin_inspect_router is not None:  # pragma: no cover - import-time wiring
    from fastapi import APIRouter as _APIRouter

    # include sub-router endpoints under /admin/* paths
    router.include_router(admin_inspect_router)


# ---------------------------------------------------------------------------
# Admin: TV Config (docs & examples)
# ---------------------------------------------------------------------------

_TV_CFG_EXAMPLE = {
    "status": "ok",
    "config": {
        "ambient_rotation": 45,
        "rail": "safe",
        "quiet_hours": {"start": "22:00", "end": "06:00"},
        "default_vibe": "Calm Night",
    },
}


@router.get(
    "/admin/tv/config",
    response_model=TvConfigResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": _TV_CFG_EXAMPLE,
                }
            }
        }
    },
)
async def admin_tv_get_config(resident_id: str, user_id: str = Depends(get_current_user_id)):
    """Mirror of /tv/config (GET) for docs under Admin tag."""
    from app.care_store import get_tv_config as _get_tv_config

    rec = await _get_tv_config(resident_id)
    if not rec:
        cfg = TvConfig()
        return {"status": "ok", "config": cfg.model_dump()}
    cfg = TvConfig(
        ambient_rotation=int(rec.get("ambient_rotation") or 30),
        rail=str(rec.get("rail") or "safe"),
        quiet_hours=QuietHours(**(rec.get("quiet_hours") or {})) if rec.get("quiet_hours") else None,
        default_vibe=str(rec.get("default_vibe") or "Calm Night"),
    )
    return {"status": "ok", "config": cfg.model_dump()}


@router.put(
    "/admin/tv/config",
    response_model=TvConfigResponse,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": _TV_CFG_EXAMPLE,
                }
            }
        }
    },
)
async def admin_tv_put_config(
    resident_id: str | None = Query(default="me"),
    body: TVConfigUpdate = None,  # type: ignore[assignment]
    user_id: str = Depends(get_current_user_id),
):
    """Mirror of /tv/config (PUT) for docs under Admin tag."""
    # Align behavior with /tv/config: allow partial updates by merging with current
    from app.care_store import get_tv_config as _get_tv_config, set_tv_config as _set_tv_config

    rec = await _get_tv_config(resident_id or "me")
    current = TvConfig(
        ambient_rotation=int((rec or {}).get("ambient_rotation") or 30),
        rail=str((rec or {}).get("rail") or "safe"),
        quiet_hours=QuietHours(**((rec or {}).get("quiet_hours") or {})) if (rec and rec.get("quiet_hours")) else None,
        default_vibe=str((rec or {}).get("default_vibe") or "Calm Night"),
    )

    new_ambient = int(body.ambient_rotation) if body and body.ambient_rotation is not None else current.ambient_rotation
    new_rail = (body.rail or current.rail).lower() if body else current.rail
    new_qh = body.quiet_hours if (body and body.quiet_hours is not None) else current.quiet_hours
    new_vibe = body.default_vibe if (body and body.default_vibe is not None) else current.default_vibe

    # minimal validation to match tv endpoint
    rail = (new_rail or "safe").lower()
    if rail not in {"safe", "admin", "open"}:
        raise HTTPException(status_code=400, detail="invalid_rail")

    def _valid_hhmm(s: str | None) -> bool:
        if not s:
            return True
        parts = s.split(":")
        if len(parts) != 2:
            return False
        try:
            hh, mm = int(parts[0]), int(parts[1])
            return 0 <= hh <= 23 and 0 <= mm <= 59
        except Exception:
            return False

    if new_qh and not (_valid_hhmm(new_qh.start) and _valid_hhmm(new_qh.end)):
        raise HTTPException(status_code=400, detail="invalid_quiet_hours")

    await _set_tv_config(
        resident_id or "me",
        ambient_rotation=int(new_ambient),
        rail=rail,
        quiet_hours=new_qh.model_dump() if new_qh else None,
        default_vibe=str(new_vibe or ""),
    )
    return {"status": "ok", "config": {
        "ambient_rotation": new_ambient,
        "rail": rail,
        "quiet_hours": new_qh.model_dump() if new_qh else None,
        "default_vibe": new_vibe,
    }}


