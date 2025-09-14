"""Temporary compatibility bridge for prompt routing.

This shim forwards to the DI-bound prompt router when possible (the one
bound on ``app.state.prompt_router`` by startup). When running outside a
FastAPI request/app context it falls back to a light-weight config-based
resolver that mirrors the startup logic.  Log usage so we can track legacy
calls and remove this bridge after migration.
"""

from __future__ import annotations

import logging
from typing import Any

from app.errors import BackendUnavailableError

from .config import CONFIG
from .hooks import run_post_hooks as _run_post_hooks
from .state import HEALTH

logger = logging.getLogger(__name__)


async def route_prompt(*args, **kwargs) -> dict[str, Any]:
    """Compatibility entrypoint used by both legacy and new callers.

    Prefer the DI-bound router on ``app.main.app.state.prompt_router`` when
    available. Otherwise, resolve by configuration (mirrors startup) and
    call the concrete backend module directly.
    """
    # Import here to avoid cycles and keep module light
    try:
        from app.api.ask_contract import AskRequest as _AskRequest  # type: ignore
    except Exception:
        _AskRequest = None  # type: ignore

    payload_or_request = args[0] if len(args) >= 1 else kwargs.get("payload")
    # Normalize to a flat payload dict supporting legacy signature variants
    if _AskRequest is not None and isinstance(payload_or_request, _AskRequest):  # type: ignore[arg-type]
        req = payload_or_request
        payload: dict[str, Any] = {
            "prompt": req.text,
            "session_id": req.session_id,
            "model_override": req.model_override,
            "intent_hint": req.intent_hint,
            "metadata": req.metadata or {},
        }
        kwargs.get("user_id")
    elif isinstance(payload_or_request, dict):
        payload = payload_or_request
        payload.get("user_id") or kwargs.get("user_id")
    elif len(args) >= 2 and isinstance(args[0], str):
        # Legacy: route_prompt(prompt_text, user_id, **kwargs)
        payload = {
            "prompt": args[0],
            "model_override": kwargs.get("model_override"),
            "metadata": kwargs.get("metadata") or {},
        }
        args[1]
    else:
        payload = {"prompt": str(payload_or_request)}
        kwargs.get("user_id")

    # Non-blocking health snapshot: never await in request path
    payload.setdefault("health_snapshot", HEALTH.get_snapshot())

    # Skill selection (lazy registry): choose by confidence / max(0.01, cost)
    try:
        from app.api.ask_contract import AskRequest as _AskRequest2
        from app.skills.registry import REGISTRY, register_builtin_skills

        register_builtin_skills()  # idempotent
        text = str(payload.get("prompt") or "")
        intent_hint = payload.get("intent_hint")

        best_skill = None
        best_score = 0.0
        for sk in REGISTRY.list():
            try:
                if not sk.can_handle(text, intent_hint):
                    continue
                conf = float(sk.confidence(text, intent_hint))
                cost = max(0.01, float(sk.cost_estimate(text)))
                score = conf / cost
                if score > best_score:
                    best_score = score
                    best_skill = sk
            except Exception:
                continue

        if best_skill is not None and best_score >= 0.6:
            req = _AskRequest2(
                text=text,
                session_id=payload.get("session_id"),
                stream=False,
                model_override=payload.get("model_override"),
                intent_hint=intent_hint,
                metadata=payload.get("metadata") or {},
            )
            result = await best_skill.run(req)
            # Ensure result has required fields for post-processing/cache
            result.setdefault("usage", {})
            result.setdefault("vendor", "skill")
            result.setdefault("model", best_skill.name)
            result.setdefault("cache_hit", False)
            obs = result.setdefault("observability", {})
            rd = obs.setdefault("route_decision", {})
            rd.setdefault("skill_won", best_skill.name)
            try:
                obs["hooks"] = await _run_post_hooks(result, req)
            except Exception:
                # Never break request path due to hooks
                obs["hooks"] = {"results": [], "ok": True}
            return result
    except Exception:
        # Skills are optional; on any error continue to LLM routing
        pass


# Public hook runner (kept here for a stable import path)
async def run_post_hooks(result: dict[str, Any], request: Any) -> dict[str, Any]:  # type: ignore[override]
    try:
        return await _run_post_hooks(result, request)
    except Exception:
        # Never propagate
        return {"results": [], "ok": True}

    # In-process semantic cache (non-blocking)
    try:
        from .state import SEM_CACHE, ensure_usage_ints, make_semantic_cache_key

        key = make_semantic_cache_key(
            user_id=user_id or "anon",
            prompt_text=str(payload.get("prompt") or ""),
        )
        cached = SEM_CACHE.get(key)
        if cached is not None:
            # Mark cache hit and return a shallow copy
            hit = dict(cached)
            hit["cache_hit"] = True
            return hit
    except Exception:
        # Ignore cache failures
        pass
    # 1) Try to use the running FastAPI app instance if present
    try:
        # Prefer registry-configured router when available (keeps legacy behavior)
        try:
            from .registry import get_router

            router = get_router()
            if router is not None:
                logger.info("compat.route_prompt: using registry router")
                result = await router.route_prompt(payload)
                # Post-execution hooks (supervised)
                try:
                    # Build a minimal AskRequest for hooks
                    from app.api.ask_contract import AskRequest as _AR

                    req = _AR(
                        text=str(payload.get("prompt") or ""),
                        session_id=payload.get("session_id"),
                        stream=False,
                        model_override=payload.get("model_override"),
                        intent_hint=payload.get("intent_hint"),
                        metadata=payload.get("metadata") or {},
                    )
                    result.setdefault("observability", {})
                    result["observability"]["hooks"] = await _run_post_hooks(
                        result, req
                    )
                    rd = result["observability"].setdefault("route_decision", {})
                    rd.setdefault("skill_won", None)
                    rd.setdefault("intent", payload.get("intent_hint") or "")
                    rd.setdefault(
                        "model",
                        result.get("model") or payload.get("model_override") or "",
                    )
                    rd.setdefault("vendor", result.get("vendor") or "")
                    rd.setdefault("cache_hit", bool(result.get("cache_hit")))
                except Exception:
                    result.setdefault("observability", {})
                    result["observability"]["hooks"] = {"results": [], "ok": True}
                    result["observability"].setdefault(
                        "route_decision",
                        {
                            "skill_won": None,
                            "intent": payload.get("intent_hint") or "",
                            "model": result.get("model")
                            or payload.get("model_override")
                            or "",
                            "vendor": result.get("vendor") or "",
                            "cache_hit": bool(result.get("cache_hit")),
                        },
                    )
                try:
                    result.setdefault("usage", {})
                    ensure_usage_ints(result["usage"])  # type: ignore[index]
                    result.setdefault("cache_hit", False)
                    SEM_CACHE.set(key, dict(result))  # type: ignore[arg-type]
                except Exception:
                    pass
                return result
        except Exception:
            # registry not configured or unavailable, continue
            pass

        from app.main import app as main_app

        prompt_router = getattr(main_app.state, "prompt_router", None)
        if prompt_router:
            logger.info("compat.route_prompt: using app.state.prompt_router")
            result = await prompt_router(payload)
            # Post-execution hooks (supervised)
            try:
                from app.api.ask_contract import AskRequest as _AR

                req = _AR(
                    text=str(payload.get("prompt") or ""),
                    session_id=payload.get("session_id"),
                    stream=False,
                    model_override=payload.get("model_override"),
                    intent_hint=payload.get("intent_hint"),
                    metadata=payload.get("metadata") or {},
                )
                result.setdefault("observability", {})
                result["observability"]["hooks"] = await _run_post_hooks(result, req)
                rd = result["observability"].setdefault("route_decision", {})
                rd.setdefault("skill_won", None)
                rd.setdefault("intent", payload.get("intent_hint") or "")
                rd.setdefault(
                    "model", result.get("model") or payload.get("model_override") or ""
                )
                rd.setdefault("vendor", result.get("vendor") or "")
                rd.setdefault("cache_hit", bool(result.get("cache_hit")))
            except Exception:
                result.setdefault("observability", {})
                result["observability"]["hooks"] = {"results": [], "ok": True}
                result["observability"].setdefault(
                    "route_decision",
                    {
                        "skill_won": None,
                        "intent": payload.get("intent_hint") or "",
                        "model": result.get("model")
                        or payload.get("model_override")
                        or "",
                        "vendor": result.get("vendor") or "",
                        "cache_hit": bool(result.get("cache_hit")),
                    },
                )
            try:
                result.setdefault("usage", {})
                ensure_usage_ints(result["usage"])  # type: ignore[index]
                result.setdefault("cache_hit", False)
                SEM_CACHE.set(key, dict(result))  # type: ignore[arg-type]
            except Exception:
                pass
            return result
    except Exception as e:  # pragma: no cover - best-effort compatibility
        logger.debug("compat.route_prompt: failed to use app.state (%s)", e)

    # 2) Fallback: light-weight config-based resolver (mirrors startup binding)
    try:
        backend = CONFIG.prompt_backend if not CONFIG.dry_run else "dryrun"
    except Exception:
        backend = "dryrun"

    logger.info(
        "compat.route_prompt: falling back to config resolver backend=%s", backend
    )

    try:
        if backend == "openai":
            from app.routers.openai_router import openai_router

            logger.warning(
                "compat.route_prompt: calling OpenAI backend via bridge (legacy path)"
            )
            result = await openai_router(payload)
            try:
                from app.api.ask_contract import AskRequest as _AR

                req = _AR(
                    text=str(payload.get("prompt") or ""),
                    session_id=payload.get("session_id"),
                    stream=False,
                    model_override=payload.get("model_override"),
                    intent_hint=payload.get("intent_hint"),
                    metadata=payload.get("metadata") or {},
                )
                result.setdefault("observability", {})
                result["observability"]["hooks"] = await _run_post_hooks(result, req)
                rd = result["observability"].setdefault("route_decision", {})
                rd.setdefault("skill_won", None)
                rd.setdefault("intent", payload.get("intent_hint") or "")
                rd.setdefault(
                    "model", result.get("model") or payload.get("model_override") or ""
                )
                rd.setdefault("vendor", result.get("vendor") or "")
                rd.setdefault("cache_hit", bool(result.get("cache_hit")))
            except Exception:
                result.setdefault("observability", {})
                result["observability"]["hooks"] = {"results": [], "ok": True}
                result["observability"].setdefault(
                    "route_decision",
                    {
                        "skill_won": None,
                        "intent": payload.get("intent_hint") or "",
                        "model": result.get("model")
                        or payload.get("model_override")
                        or "",
                        "vendor": result.get("vendor") or "",
                        "cache_hit": bool(result.get("cache_hit")),
                    },
                )
            try:
                result.setdefault("usage", {})
                ensure_usage_ints(result["usage"])  # type: ignore[index]
                result.setdefault("cache_hit", False)
                SEM_CACHE.set(key, dict(result))  # type: ignore[arg-type]
            except Exception:
                pass
            return result
        elif backend == "llama":
            from app.routers.llama_router import llama_router

            logger.warning(
                "compat.route_prompt: calling LLaMA backend via bridge (legacy path)"
            )
            result = await llama_router(payload)
            try:
                from app.api.ask_contract import AskRequest as _AR

                req = _AR(
                    text=str(payload.get("prompt") or ""),
                    session_id=payload.get("session_id"),
                    stream=False,
                    model_override=payload.get("model_override"),
                    intent_hint=payload.get("intent_hint"),
                    metadata=payload.get("metadata") or {},
                )
                result.setdefault("observability", {})
                result["observability"]["hooks"] = await _run_post_hooks(result, req)
            except Exception:
                result.setdefault("observability", {})
                result["observability"]["hooks"] = {"results": [], "ok": True}
            try:
                result.setdefault("usage", {})
                ensure_usage_ints(result["usage"])  # type: ignore[index]
                result.setdefault("cache_hit", False)
                SEM_CACHE.set(key, dict(result))  # type: ignore[arg-type]
            except Exception:
                pass
            return result
        else:
            logger.warning("compat.route_prompt: dryrun fallback used (legacy path)")
            return {"dry_run": True, "echo": payload}
    except Exception as e:
        logger.exception("compat.route_prompt: backend call failed: %s", e)
        raise BackendUnavailableError(str(e))
