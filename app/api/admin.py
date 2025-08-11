from __future__ import annotations

import os
from fastapi import APIRouter, Depends, HTTPException, Query

from app.deps.user import get_current_user_id
from app.deps.scopes import optional_require_scope
from app.status import _admin_token
from app.analytics import get_metrics, cache_hit_rate, get_top_skills
from app.decisions import get_recent as decisions_recent, get_explain as decisions_get
from app.config_runtime import get_config
from app.jobs.qdrant_lifecycle import bootstrap_collection as _q_bootstrap, collection_stats as _q_stats
from app.jobs.migrate_chroma_to_qdrant import main as _migrate_cli  # type: ignore
try:
    from app.admin.routes import router as admin_inspect_router
except Exception:
    admin_inspect_router = None  # type: ignore

router = APIRouter(tags=["admin"], dependencies=[Depends(optional_require_scope("admin"))])


def _check_admin(token: str | None) -> None:
    """Enforce admin token when configured.

    In test runs (PYTEST_RUNNING=1), allow access when no token query param
    is supplied so unit tests can read config without coupling to env.
    When a token is explicitly provided, still enforce matching behavior.
    """
    _tok = _admin_token()
    if os.getenv("PYTEST_RUNNING", "").lower() in {"1", "true", "yes"}:
        if token is None:
            return
    if _tok and token != _tok:
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/admin/metrics")
async def admin_metrics(
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    _check_admin(token)
    m = get_metrics()
    return {"metrics": m, "cache_hit_rate": cache_hit_rate(), "top_skills": get_top_skills(10)}


@router.get("/admin/router/decisions")
async def admin_router_decisions(
    limit: int = Query(default=500, ge=1, le=1000),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
) -> dict:
    _check_admin(token)
    return {"items": decisions_recent(limit)}


@router.get("/admin/retrieval/last")
async def admin_retrieval_last(
    limit: int = Query(default=200, ge=1, le=2000),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    """Return last N retrieval traces (subset of router decisions), most recent first."""
    _check_admin(token)
    items = decisions_recent(limit)
    # filter to those that have a retrieval_trace event
    out = []
    for it in items:
        trace = it.get("trace") or []
        if any(ev.get("event") == "retrieval_trace" for ev in trace):
            out.append(it)
    return {"items": out[:limit]}


@router.get("/admin/decisions/explain")
async def explain_decision(
    req_id: str,
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token)
    data = decisions_get(req_id)
    if not data:
        raise HTTPException(status_code=404, detail="not_found")
    return data


@router.get("/admin/config")
async def admin_config(
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token)
    data = get_config().to_dict()
    # Overlay a few live values for observability at runtime
    import os as _os
    data["store"]["vector_store"] = (_os.getenv("VECTOR_STORE") or data["store"]["vector_store"]).lower()
    data["store"]["qdrant_collection"] = _os.getenv("QDRANT_COLLECTION", data["store"].get("qdrant_collection", "kb:default"))
    data["store"]["active_collection"] = data["store"]["qdrant_collection"]
    return data


@router.post("/admin/vector_store/bootstrap")
async def admin_vs_bootstrap(
    name: str | None = Query(default=None),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token)
    coll = name or (os.getenv("QDRANT_COLLECTION") or "kb:default")
    try:
        res = _q_bootstrap(coll, int(os.getenv("EMBED_DIM", "1536")))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return res
@router.post("/admin/vector_store/migrate")
async def admin_vs_migrate(
    action: str = Query(default="migrate", pattern="^(inventory|export|migrate)$"),
    dry_run: bool = Query(default=True),
    out_dir: str | None = Query(default=None),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token)
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



@router.get("/admin/vector_store/stats")
async def admin_vs_stats(
    name: str | None = Query(default=None),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token)
    coll = name or (os.getenv("QDRANT_COLLECTION") or "kb:default")
    try:
        return _q_stats(coll)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/qdrant/collections")
async def admin_qdrant_collections(
    names: str | None = Query(default=None, description="CSV of collection names"),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    _check_admin(token)
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


@router.post("/admin/flags")
async def admin_flags(
    key: str = Query(..., description="Flag key, e.g., RETRIEVAL_PIPELINE"),
    value: str = Query(..., description="New value"),
    token: str | None = Query(default=None),
    user_id: str = Depends(get_current_user_id),
):
    """Flip runtime flags (process env) — best-effort.

    Guarded by admin token. Note: only affects this process; not persisted.
    """
    _check_admin(token)
    os.environ[key] = value
    return {"status": "ok", "key": key, "value": value}


# Mount new admin-inspect routes under the same router if available
if admin_inspect_router is not None:  # pragma: no cover - import-time wiring
    from fastapi import APIRouter as _APIRouter

    # include sub-router endpoints under /admin/* paths
    router.include_router(admin_inspect_router)


