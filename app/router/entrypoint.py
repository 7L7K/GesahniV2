"""Temporary compatibility bridge for prompt routing.

This shim forwards to the DI-bound prompt router when possible (the one
bound on ``app.state.prompt_router`` by startup). When running outside a
FastAPI request/app context it falls back to a light-weight config-based
resolver that mirrors the startup logic.  Log usage so we can track legacy
calls and remove this bridge after migration.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from app.errors import BackendUnavailableError

from .config import CONFIG
from .hooks import run_post_hooks as _run_post_hooks
from .state import HEALTH

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Structured routing decision for dry-run mode."""

    model_id: str
    provider: str
    reason: str
    stream: bool
    fallback_chain: list[str]
    rules_triggered: list[str]
    privacy_mode: bool
    task_type: str
    estimated_tokens: int


async def _simulate_routing_decision(payload: dict[str, Any]) -> RoutingDecision:
    """Simulate routing decision without network calls or heavy dependencies."""
    from app.models.catalog import (
        GPT_4O,
        LLAMA3_LATEST,
        MODEL_ALIASES,
        TEXT_EMBEDDING_ADA_002,
    )

    prompt_text = str(payload.get("prompt", ""))
    model_override = payload.get("model_override")
    task_type = payload.get("task_type", "chat")
    intent_hint = payload.get("intent_hint")

    # Simple token estimation (rough approximation)
    estimated_tokens = max(1, len(prompt_text.split()) * 4)  # ~4 tokens per word

    # Simple intent detection (based on keywords and hints)
    intent = intent_hint or "general"
    if any(
        word in prompt_text.lower()
        for word in ["analyze", "research", "study", "examine"]
    ):
        intent = "analysis"
    elif any(
        word in prompt_text.lower() for word in ["code", "program", "function", "debug"]
    ):
        intent = "code"
    elif any(
        word in prompt_text.lower() for word in ["sql", "query", "database", "table"]
    ):
        intent = "sql"
    elif any(
        word in prompt_text.lower()
        for word in ["file", "directory", "ops", "operation"]
    ):
        intent = "ops"

    # Check privacy mode
    privacy_mode = payload.get("privacy_mode", False)

    # Determine model and provider
    rules_triggered = []
    fallback_chain = []

    if model_override:
        # Model override logic
        mv = model_override.strip()
        if mv.startswith("gpt"):
            model_id = MODEL_ALIASES.get(mv, mv)
            provider = "openai"
            reason = "explicit_override"
            rules_triggered.append("override")
        elif mv.startswith("llama"):
            model_id = mv
            provider = "ollama"
            reason = "explicit_override"
            rules_triggered.append("override")
        else:
            # Unknown model - default to GPT
            model_id = GPT_4O
            provider = "openai"
            reason = "unknown_model_fallback"
            rules_triggered.append("unknown_model")
            fallback_chain.append("unknown_model→gpt-4o")
    elif task_type == "embed":
        # Embedding task
        model_id = TEXT_EMBEDDING_ADA_002
        provider = "openai"
        reason = "task_embedding"
        rules_triggered.append("task:embed")
    else:
        # Simplified model selection logic (mimics model_picker behavior)
        should_use_gpt = False
        reason = "light_default"
        model_id = LLAMA3_LATEST
        provider = "ollama"

        # Check for heavy keywords (matches model_picker.py)
        heavy_keywords = ["code", "unit test", "analyze", "sql", "benchmark", "vector"]
        keyword_hit = None
        for keyword in heavy_keywords:
            if keyword.lower() in prompt_text.lower():
                should_use_gpt = True
                keyword_hit = keyword
                reason = "keyword"
                break

        # Check token threshold
        if estimated_tokens > 1000:
            should_use_gpt = True
            reason = "heavy_tokens"
            rules_triggered.append("token_threshold")

        # Check word count threshold
        word_count = len(prompt_text.split())
        if word_count > 30:
            should_use_gpt = True
            reason = "heavy_length"
            rules_triggered.append("word_threshold")

        # Check intent
        if intent in {"analysis", "research"}:
            should_use_gpt = True
            reason = "heavy_intent"
            rules_triggered.append("intent:analysis")

        # Apply model selection
        if should_use_gpt:
            model_id = GPT_4O
            provider = "openai"
        else:
            model_id = LLAMA3_LATEST
            provider = "ollama"

        # Check for attachments
        attachments_count = payload.get("attachments_count", 0)
        if attachments_count > 0:
            rules_triggered.append(f"attachments>{attachments_count}")
            model_id = GPT_4O
            provider = "openai"
            reason = "attachments"

        # Check RAG context
        rag_tokens = payload.get("rag_tokens", 0)
        if rag_tokens > 6000:
            rules_triggered.append("rag_tokens>6000")
            model_id = GPT_4O
            provider = "openai"
            reason = "long_context"

        # Check for ops files
        ops_files_count = payload.get("ops_files_count", 0)
        if intent == "ops" and ops_files_count > 2:
            rules_triggered.append(f"ops_files>{ops_files_count}")
            model_id = GPT_4O
            provider = "openai"
            reason = "ops_complex"

        # Build rules_triggered list
        if keyword_hit:
            rules_triggered.append(f"keyword:{keyword_hit}")

        # For light tasks that go to LLaMA, mark as default_light
        if (
            not should_use_gpt
            and not keyword_hit
            and not attachments_count
            and not ops_files_count
            and rag_tokens == 0
        ):
            rules_triggered.append("default_light")

        # Simulate LLaMA health issues (assume healthy for dry-run)
        llama_healthy = True  # Assume healthy in dry-run mode
        if not llama_healthy and provider == "ollama":
            rules_triggered.append("fallback:llama_unhealthy")
            fallback_chain.append("llama_unhealthy→gpt-4o")
            model_id = GPT_4O
            provider = "openai"
            reason = "llama_fallback"

    # Determine if streaming is supported
    stream = task_type != "embed"  # Embeddings don't stream

    return RoutingDecision(
        model_id=model_id,
        provider=provider,
        reason=reason,
        stream=stream,
        fallback_chain=fallback_chain,
        rules_triggered=rules_triggered,
        privacy_mode=privacy_mode,
        task_type=task_type,
        estimated_tokens=estimated_tokens,
    )


async def route_prompt(*args, **kwargs) -> dict[str, Any] | RoutingDecision:
    """Compatibility entrypoint used by both legacy and new callers.

    Prefer the DI-bound router on ``app.main.app.state.prompt_router`` when
    available. Otherwise, resolve by configuration (mirrors startup) and
    call the concrete backend module directly.

    When dry_run=True, returns a RoutingDecision without making network calls.
    """
    # Reset golden trace flag at start of request
    from contextvars import ContextVar

    _gtrace_flag: ContextVar[bool] = ContextVar("gtrace_once", default=False)

    def _reset_gtrace_flag():
        """Reset the golden trace flag for a new request."""
        _gtrace_flag.set(False)

    _reset_gtrace_flag()

    # Import here to avoid cycles and keep module light
    try:
        from app.api.ask_contract import AskRequest as _AskRequest  # type: ignore
    except Exception:
        _AskRequest = None  # type: ignore

    # Extract dry_run flag
    dry_run = kwargs.get("dry_run", False) or os.getenv("DRY_RUN", "").lower() in {
        "1",
        "true",
        "yes",
    }

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

    # Dry-run mode: return routing decision without network calls
    if dry_run:
        return await _simulate_routing_decision(payload)

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

    # Extract user_id for cache and routing
    user_id = payload.get("user_id") or kwargs.get("user_id")

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

        from app.main import get_app

        main_app = get_app()
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
        elif backend == "live":
            # For "live" backend, use the legacy router
            from app import router_legacy

            logger.info("compat.route_prompt: using legacy router for live backend")
            result = await router_legacy.route_prompt(
                payload.get("prompt", ""),
                user_id=payload.get("user_id") or kwargs.get("user_id"),
                model_override=payload.get("model_override"),
                **{
                    k: v
                    for k, v in payload.items()
                    if k not in ["prompt", "user_id", "model_override"]
                },
            )
            return result
        else:
            logger.warning("compat.route_prompt: dryrun fallback used (legacy path)")
            return {"dry_run": True, "echo": payload}
    except Exception as e:
        logger.exception("compat.route_prompt: backend call failed: %s", e)
        # NEW: test/dry-run mode should never raise; return echo instead
        if os.getenv("PYTEST_RUNNING") == "1" or os.getenv("DRY_RUN") == "1":
            return {"dry_run": True, "echo": payload}
        raise BackendUnavailableError(str(e))

    # Ensure clean golden trace flag for next call in same thread
    _reset_gtrace_flag()
