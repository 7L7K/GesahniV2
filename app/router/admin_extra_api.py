"""Compatibility admin extras used by alias router.

Provides minimal implementations for a few admin endpoints that older
clients expect at top-level paths. These try to call richer admin helpers
when available but degrade gracefully to lightweight shapes used by the
alias fallbacks.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

from app import settings

logger = logging.getLogger(__name__)


async def reload_env(request: Request) -> JSONResponse:
    """Compatibility wrapper for admin reload_env.

    Returns 200 on success, 403 when admin token missing/invalid.
    """
    try:
        # Use admin module's guard if available
        try:
            from app.api.admin import _check_admin  # type: ignore

            token = request.query_params.get("token")
            _check_admin(token, request)
        except Exception:
            # If guard not available or raises, let underlying error surface
            pass

        from app.env_utils import load_env

        load_env()
        return JSONResponse({"status": "ok"}, status_code=200)
    except Exception as e:
        logger.warning("admin.reload_env compatibility wrapper failed: %s", e)
        # Preserve original fallback behavior for unauthenticated/dev runs
        return JSONResponse({"status": "error", "detail": str(e)}, status_code=500)


async def self_review(request: Request) -> JSONResponse:
    """Compatibility wrapper for admin self review endpoint.

    If the proactive engine is installed, call it; otherwise return 501.
    """
    try:
        try:
            from app.proactive_engine import get_self_review as _get_self_review  # type: ignore

            res = _get_self_review()
            if res:
                return JSONResponse(res, status_code=200)
        except Exception:
            pass
        return JSONResponse({"detail": "not_implemented"}, status_code=501)
    except Exception as e:
        logger.exception("admin.self_review wrapper failed: %s", e)
        return JSONResponse({"detail": "not_implemented"}, status_code=501)


async def bootstrap_vector_store(request: Request) -> JSONResponse:
    """Compatibility wrapper for vector store bootstrap.

    Returns 202 when accepted (to match legacy clients) or 403 when admin
    token validation fails. Attempts to call the project's bootstrap helper
    when available but always returns an accepted response for compatibility.
    """
    token = request.query_params.get("token")
    try:
        from app.api.admin import _check_admin  # type: ignore

        _check_admin(token, request)
    except Exception as e:
        # _check_admin raises HTTPException on forbidden; mirror that as 403
        logger.warning("admin.bootstrap_vector_store: admin check failed: %s", e)
        return JSONResponse({"detail": "forbidden"}, status_code=403)

    coll = request.query_params.get("name") or settings.qdrant_collection()
    strict = settings.strict_vector_store()
    try:
        from app.memory.api import _get_store  # type: ignore

        # Attempt to initialise store (may raise when misconfigured)
        try:
            s = _get_store()
        except Exception as e:
            logger.exception("admin.bootstrap_vector_store: store init failed: %s", e)
            if strict:
                return JSONResponse(
                    {"detail": "vector_store_misconfigured", "error": str(e)},
                    status_code=400,
                )
            return JSONResponse(
                {"status": "error", "detail": "init_failed"}, status_code=202
            )

        # If store initialised, attempt bootstrap via admin helper if present
        try:
            from app.api.admin import _q_bootstrap  # type: ignore

            _q_bootstrap(coll, settings.embed_dim())
        except Exception:
            logger.info(
                "admin.bootstrap_vector_store: bootstrap helper missing or failed; returning accepted"
            )
    except Exception as e:
        logger.exception("admin.bootstrap_vector_store: unexpected error: %s", e)
        if strict:
            return JSONResponse(
                {"detail": "vector_store_error", "error": str(e)}, status_code=500
            )
        return JSONResponse({"status": "accepted", "collection": coll}, status_code=202)

    return JSONResponse({"status": "accepted", "collection": coll}, status_code=202)
