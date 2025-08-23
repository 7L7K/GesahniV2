import asyncio
import inspect
import logging
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx
from fastapi import HTTPException, status

import app.llama_integration as llama_integration

from .analytics import record
from .gpt_client import SYSTEM_PROMPT, ask_gpt
from .history import append_history
from .intent_detector import detect_intent
from .llama_integration import ask_llama

# Optional prompt clamp to enforce token budgets; ignore if module absent
try:  # pragma: no cover - optional
    from .token_budgeter import clamp_prompt
except Exception:  # pragma: no cover - fallback when module missing

    def clamp_prompt(text: str, *_args, **_kwargs) -> str:
        return text


try:  # pragma: no cover - fall back if circuit flag missing
    from .llama_integration import llama_circuit_open  # type: ignore
except Exception:  # pragma: no cover - defensive
    llama_circuit_open = False  # type: ignore
from .memory.profile_store import CANONICAL_KEYS, profile_store
from .memory.vector_store import lookup_cached_answer
from .memory.write_policy import memory_write_policy
from .model_picker import pick_model
from .postcall import PostCallData, process_postcall
from .prompt_builder import PromptBuilder
from .skills.base import SKILLS as BUILTIN_CATALOG
from .skills.smalltalk_skill import SmalltalkSkill

try:  # optional: new retrieval pipeline
    from .retrieval.pipeline import run_pipeline as _run_retrieval_pipeline
except Exception:  # pragma: no cover
    _run_retrieval_pipeline = None  # type: ignore
from .token_utils import count_tokens

# Optional proactive engine hooks; ignore import errors in tests
try:  # pragma: no cover - optional
    from .proactive_engine import handle_user_reply, maybe_curiosity_prompt
except Exception:  # pragma: no cover - fallback stubs

    async def maybe_curiosity_prompt(*_a, **_k):
        return None

    def handle_user_reply(*_a, **_k):
        return None


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    """Data class to encapsulate routing decision information."""

    vendor: str
    model: str
    reason: str
    keyword_hit: str | None
    stream: bool
    allow_fallback: bool
    request_id: str


class ErrorType(Enum):
    """Normalized error types for deterministic fallback policy."""

    PROVIDER_4XX = (
        "provider_4xx"  # Client errors (400-499) - likely won't succeed on retry
    )
    PROVIDER_5XX = "provider_5xx"  # Server errors (500-599) - might succeed on retry
    NETWORK_TIMEOUT = "network_timeout"  # Network issues - might succeed on retry
    AUTH_ERROR = (
        "auth_error"  # Authentication issues - won't succeed without fixing credentials
    )


def normalize_error(error: Exception) -> ErrorType:
    """Normalize various exception types into standardized ErrorType enum."""

    # Handle HTTP status errors
    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        if 400 <= status_code < 500:
            if status_code in (401, 403):
                return ErrorType.AUTH_ERROR
            else:
                return ErrorType.PROVIDER_4XX
        elif 500 <= status_code < 600:
            return ErrorType.PROVIDER_5XX

    # Handle HTTPX specific errors
    if isinstance(
        error,
        (
            httpx.TimeoutException,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ),
    ):
        return ErrorType.NETWORK_TIMEOUT

    if isinstance(error, (httpx.ConnectError, httpx.RemoteProtocolError)):
        return ErrorType.NETWORK_TIMEOUT

    # Handle generic timeout errors
    if isinstance(error, asyncio.TimeoutError):
        return ErrorType.NETWORK_TIMEOUT

    # Handle authentication errors
    error_str = str(error).lower()
    if any(
        keyword in error_str
        for keyword in [
            "unauthorized",
            "forbidden",
            "invalid api key",
            "authentication failed",
        ]
    ):
        return ErrorType.AUTH_ERROR

    # Default to server error for unknown exceptions
    return ErrorType.PROVIDER_5XX


# ---------------------------------------------------------------------------
# Constants / Config
# ---------------------------------------------------------------------------


# Single source of truth for model allow-lists
def _get_allowed_models() -> tuple[set[str], set[str]]:
    """Get allowed models from environment variables as sets."""
    gpt_models = set(
        filter(
            None,
            os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(","),
        )
    )
    llama_models = set(
        filter(
            None, os.getenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3").split(",")
        )
    )
    return gpt_models, llama_models


ALLOWED_GPT_MODELS, ALLOWED_LLAMA_MODELS = _get_allowed_models()

# Environment variables for routing configuration
ROUTER_BUDGET_MS = int(os.getenv("ROUTER_BUDGET_MS", "7000"))
OPENAI_TIMEOUT_MS = int(os.getenv("OPENAI_TIMEOUT_MS", "6000"))
OLLAMA_TIMEOUT_MS = int(os.getenv("OLLAMA_TIMEOUT_MS", "4500"))


def _validate_model_allowlist(model: str, vendor: str) -> None:
    """Validate model against allow-list before any vendor imports."""
    if vendor == "openai":
        if model not in ALLOWED_GPT_MODELS:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "model_not_allowed",
                    "model": model,
                    "vendor": vendor,
                    "allowed": list(ALLOWED_GPT_MODELS),
                },
            )
    elif vendor == "ollama":
        if model not in ALLOWED_LLAMA_MODELS:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "model_not_allowed",
                    "model": model,
                    "vendor": vendor,
                    "allowed": list(ALLOWED_LLAMA_MODELS),
                },
            )
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unknown_model",
                "model": model,
                "hint": f"allowed: {', '.join(ALLOWED_GPT_MODELS | ALLOWED_LLAMA_MODELS)}",
            },
        )


# OpenAI circuit breaker state (similar to LLaMA pattern)
openai_failures: int = 0
openai_last_failure_ts: float = 0.0
openai_circuit_open: bool = False
OPENAI_HEALTHY: bool = True

# OpenAI health check state tracking
openai_health_check_state = {
    "has_ever_succeeded": False,
    "last_success_ts": 0.0,
    "last_check_ts": 0.0,
    "consecutive_failures": 0,
    "next_check_delay": 5.0,  # Start with 5 seconds
    "max_check_delay": 300.0,  # Max 5 minutes
    "success_throttle_delay": 60.0,  # 1 minute after success
}


def _check_vendor_health(vendor: str) -> bool:
    """Check if vendor is healthy without importing vendor modules."""
    if vendor == "openai":
        return OPENAI_HEALTHY and not openai_circuit_open
    elif vendor == "ollama":
        return (
            llama_integration.LLAMA_HEALTHY and not llama_integration.llama_circuit_open
        )
    return False


def _get_fallback_vendor(vendor: str) -> str:
    """Get the opposite vendor for fallback."""
    return "ollama" if vendor == "openai" else "openai"


def _get_fallback_model(vendor: str) -> str:
    """Get the default model for the fallback vendor."""
    if vendor == "openai":
        return "gpt-4o"  # Default GPT model
    else:
        return "llama3"  # Default LLaMA model


def _dry(engine: str, model: str) -> str:
    """Dry run function for testing."""
    label = model.split(":")[0] if engine == "llama" else model
    msg = f"[dry-run] would call {engine} {label}"
    logger.info(msg)
    return msg


import json
import uuid
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Post-call handling (use existing postcall.py module)
# ---------------------------------------------------------------------------


def _log_golden_trace(
    request_id: str,
    user_id: str | None,
    path: str,
    shape: str,
    normalized_from: str | None,
    override_in: str | None,
    intent: str,
    tokens_est: int,
    routing_decision: RoutingDecision,
    dry_run: bool,
    cb_user_open: bool,
    cb_global_open: bool,
    tokens_est_method: str = "approx",
    latency_ms: int | None = None,
    timeout_ms: int | None = None,
    fallback_reason: str | None = None,
    cache_hit: bool = False,
) -> None:
    """Emit exactly one post-decision log before adapter call. Make it the law."""
    trace = {
        "ts": datetime.now(UTC).isoformat(),
        "rid": request_id,
        "uid": user_id,
        "path": path,
        "shape": shape,
        "normalized_from": normalized_from,
        "override_in": override_in,
        "intent": intent,
        "tokens_est": tokens_est,
        "tokens_est_method": tokens_est_method,
        "picker_reason": routing_decision.reason,
        "chosen_vendor": routing_decision.vendor,
        "chosen_model": routing_decision.model,
        "dry_run": dry_run,
        "cb_user_open": cb_user_open,
        "cb_global_open": cb_global_open,
        "allow_fallback": routing_decision.allow_fallback,
        "stream": routing_decision.stream,
        "latency_ms": latency_ms,
        "timeout_ms": timeout_ms,
        "fallback_reason": fallback_reason,
        "cache_hit": cache_hit,
    }

    if routing_decision.keyword_hit:
        trace["keyword_hit"] = routing_decision.keyword_hit

    logger.info("🎯 GOLDEN_TRACE: %s", json.dumps(trace))

    # Emit metrics
    try:
        from .metrics import ROUTER_REQUESTS_TOTAL, normalize_model_label

        # Use normalized model label to prevent cardinality explosion
        normalized_model = normalize_model_label(routing_decision.model)
        ROUTER_REQUESTS_TOTAL.labels(
            vendor=routing_decision.vendor,
            model=normalized_model,
            reason=routing_decision.reason,
        ).inc()
    except Exception:
        pass


def _log_routing_decision(
    override_in: str | None,
    intent: str,
    tokens_est: int,
    picker_reason: str,
    chosen_vendor: str,
    chosen_model: str,
    dry_run: bool,
    cb_user_open: bool,
    cb_global_open: bool,
    shape: str,
    normalized_from: str | None,
) -> None:
    """Log the final routing decision for auditability."""
    logger.info(
        "🎯 ROUTING DECISION: override_in=%s, intent=%s, tokens_est=%s, picker_reason=%s, chosen_vendor=%s, chosen_model=%s, dry_run=%s, cb_user_open=%s, cb_global_open=%s, shape=%s, normalized_from=%s",
        override_in,
        intent,
        tokens_est,
        picker_reason,
        chosen_vendor,
        chosen_model,
        dry_run,
        cb_user_open,
        cb_global_open,
        shape,
        normalized_from,
        extra={
            "meta": {
                "override_in": override_in,
                "intent": intent,
                "tokens_est": tokens_est,
                "picker_reason": picker_reason,
                "chosen_vendor": chosen_vendor,
                "chosen_model": chosen_model,
                "dry_run": dry_run,
                "cb_user_open": cb_user_open,
                "cb_global_open": cb_global_open,
                "shape": shape,
                "normalized_from": normalized_from,
            }
        },
    )


CATALOG = BUILTIN_CATALOG  # allows tests to monkey‑patch
_SMALLTALK = SmalltalkSkill()

# Mirror of llama_integration health flag so tests can adjust routing.
LLAMA_HEALTHY: bool = True

# ---------------------------------------------------------------------------
# Per-user LLaMA circuit breaker (local to router)
# ---------------------------------------------------------------------------
_USER_CB_THRESHOLD = int(os.getenv("LLAMA_USER_CB_THRESHOLD", "3"))
_USER_CB_COOLDOWN = float(os.getenv("LLAMA_USER_CB_COOLDOWN", "120"))
_llama_user_failures: dict[str, tuple[int, float]] = {}
_llama_user_failures_lock = asyncio.Lock()


async def _user_circuit_open(user_id: str) -> bool:
    async with _llama_user_failures_lock:
        rec = _llama_user_failures.get(user_id)
        if not rec:
            return False
        count, last_ts = rec
        if (
            count >= _USER_CB_THRESHOLD
            and (__import__("time")).time() - last_ts < _USER_CB_COOLDOWN
        ):
            return True
        return False


async def _user_cb_record_failure(user_id: str) -> None:
    async with _llama_user_failures_lock:
        t = __import__("time").time()
        count, last_ts = _llama_user_failures.get(user_id, (0, 0.0))
        if t - last_ts >= _USER_CB_COOLDOWN:
            count = 0
        _llama_user_failures[user_id] = (count + 1, t)


async def _user_cb_reset(user_id: str) -> None:
    async with _llama_user_failures_lock:
        _llama_user_failures.pop(user_id, None)


# ---------------------------------------------------------------------------
# OpenAI circuit breaker functions
# ---------------------------------------------------------------------------


def _openai_record_failure() -> None:
    """Update OpenAI circuit breaker failure counters."""
    global openai_failures, openai_circuit_open, openai_last_failure_ts
    now = time.monotonic()
    if now - openai_last_failure_ts > 60:
        openai_failures = 1
    else:
        openai_failures += 1
    openai_last_failure_ts = now
    if openai_failures >= 3:
        openai_circuit_open = True


def _openai_reset_failures() -> None:
    """Reset OpenAI circuit breaker state after a successful call."""
    global openai_failures, openai_circuit_open
    openai_failures = 0
    openai_circuit_open = False


def _mark_openai_unhealthy() -> None:
    """Flip the shared health flag so the picker knows OpenAI is down."""
    global OPENAI_HEALTHY
    OPENAI_HEALTHY = False


async def _check_openai_health() -> None:
    """Attempt a minimal OpenAI call to check health and update flags."""
    global OPENAI_HEALTHY

    now = time.monotonic()

    # Check if we should skip this health check due to throttling
    if openai_health_check_state["has_ever_succeeded"]:
        time_since_success = now - openai_health_check_state["last_success_ts"]
        if time_since_success < openai_health_check_state["success_throttle_delay"]:
            logger.debug(
                "Skipping OpenAI health check - throttled after success (%.1fs remaining)",
                openai_health_check_state["success_throttle_delay"]
                - time_since_success,
            )
            return

    # Check if we should skip due to exponential backoff
    time_since_last_check = now - openai_health_check_state["last_check_ts"]
    if (
        not openai_health_check_state["has_ever_succeeded"]
        and time_since_last_check < openai_health_check_state["next_check_delay"]
    ):
        logger.debug(
            "Skipping OpenAI health check - exponential backoff (%.1fs remaining)",
            openai_health_check_state["next_check_delay"] - time_since_last_check,
        )
        return

    openai_health_check_state["last_check_ts"] = now

    try:
        # Use minimal generation to keep health checks snappy
        model = os.getenv("OPENAI_MODEL", "gpt-4o")
        text, _, _, _ = await ask_gpt(
            "ping",
            model,
            "You are a helpful assistant.",
            timeout=OPENAI_TIMEOUT_MS / 1000,
            allow_test=True,
            routing_decision=None,
        )

        # Success - update state
        OPENAI_HEALTHY = True
        openai_health_check_state["has_ever_succeeded"] = True
        openai_health_check_state["last_success_ts"] = now
        openai_health_check_state["consecutive_failures"] = 0
        openai_health_check_state["next_check_delay"] = 5.0  # Reset to initial delay

        logger.debug("OpenAI health check successful")

    except Exception as e:
        OPENAI_HEALTHY = False
        openai_health_check_state["consecutive_failures"] += 1

        # Exponential backoff: double the delay, capped at max_delay
        if not openai_health_check_state["has_ever_succeeded"]:
            openai_health_check_state["next_check_delay"] = min(
                openai_health_check_state["next_check_delay"] * 2,
                openai_health_check_state["max_check_delay"],
            )

        logger.warning("OpenAI health check failed: %s", e)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mark_llama_unhealthy() -> None:
    """Flip the shared health flag so the picker knows LLaMA is down."""
    global LLAMA_HEALTHY
    LLAMA_HEALTHY = False
    llama_integration.LLAMA_HEALTHY = False


def _fact_from_qa(question: str, answer: str) -> str:
    """Return a compact, one-line fact from a Q/A pair.

    Heuristic: prefer a single-sentence paraphrase. Fall back to trimmed answer.
    """
    q = (question or "").strip().replace("\n", " ")
    a = (answer or "").strip().replace("\n", " ")
    if not q or not a:
        return a or q
    # If the answer looks like a clean sentence, keep first sentence.
    for sep in [". ", "? ", "! "]:
        if sep in a:
            a = a.split(sep, 1)[0].strip().rstrip(".?!")
            break
    # Build a simple fact string. Keep it short.
    if len(a) <= 140:
        return a
    # If too long, summarize minimally using a hard cap.
    return (a[:137] + "...") if len(a) > 140 else a


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _low_conf(resp: str) -> bool:
    import re

    if not resp.strip():
        return True
    if re.search(r"\b(i don't know|i am not sure|not sure|cannot help)\b", resp, re.I):
        return True
    return False


def _needs_rag(prompt: str) -> bool:
    p = prompt.lower()
    return "what happened in detroit in 1968" in p or "what did i watch yesterday" in p


def _classify_profile_question(text: str) -> tuple[bool, str | None]:
    """Return (is_profile_fact, canonical_key|None).

    Simple heuristic mapper for short asks like "what's my favorite color".
    """
    p = (text or "").lower().strip()
    # map phrases to canonical keys
    mapping = {
        "favorite color": "favorite_color",
        "favourite color": "favorite_color",
        "name": "preferred_name",
        "preferred name": "preferred_name",
        "timezone": "timezone",
        "time zone": "timezone",
        "locale": "locale",
        "home city": "home_city",
        "city do i live": "home_city",
        "music service": "music_service",
        "spotify or apple": "music_service",
    }
    for phrase, key in mapping.items():
        if phrase in p:
            return True, key
    # generic patterns
    if p.startswith("what's my ") or p.startswith("what is my "):
        for key in CANONICAL_KEYS:
            if key.replace("_", " ") in p:
                return True, key
    return False, None


def _maybe_extract_confirmation(text: str) -> str | None:
    """If text cleanly states a value (e.g., "it's blue"), return the value."""
    t = (text or "").strip().strip(". ")
    lowers = t.lower()
    for prefix in ("it's ", "its ", "it is ", "is ", "= "):
        if lowers.startswith(prefix):
            return t[len(prefix) :].strip()
    # "blue" as a single token confirmation
    if len(t.split()) <= 3 and len(t) <= 32:
        return t
    return None


_BASIC_COLORS: set[str] = {
    "red",
    "blue",
    "green",
    "yellow",
    "purple",
    "orange",
    "pink",
    "black",
    "white",
    "gray",
    "grey",
    "brown",
    "teal",
    "cyan",
    "magenta",
    "maroon",
    "navy",
    "gold",
    "silver",
}


def _maybe_update_profile_from_statement(user_id: str, text: str) -> bool:
    """Parse simple statements and upsert profile facts.

    Examples:
    - "my favorite color is blue" → favorite_color=blue
    - "it's blue" → favorite_color=blue (when value is a known color)
    - "call me Alex" / "my name is Alex" → preferred_name=Alex
    - "i live in Detroit" → home_city=Detroit
    """
    t = (text or "").strip()
    tl = t.lower()
    updated = False
    try:
        # favorite color variants
        for phrase in (
            "my favorite color is ",
            "my favourite color is ",
            "favorite color is ",
            "favourite color is ",
        ):
            if tl.startswith(phrase):
                val = t[len(phrase) :].strip(" .")
                if val and memory_write_policy.should_write_profile(
                    text, "favorite_color"
                ):
                    profile_store.upsert(
                        user_id, "favorite_color", val, source="utterance"
                    )
                    updated = True
                    return True
        # generic color-only confirmation
        conf = _maybe_extract_confirmation(t)
        if conf and conf.lower() in _BASIC_COLORS:
            if memory_write_policy.should_write_profile(text, "favorite_color"):
                profile_store.upsert(
                    user_id, "favorite_color", conf, source="utterance"
                )
                return True
        # name
        for phrase in ("my name is ", "call me "):
            if tl.startswith(phrase):
                val = t[len(phrase) :].strip(" .")
                if val and memory_write_policy.should_write_profile(
                    text, "preferred_name"
                ):
                    profile_store.upsert(
                        user_id, "preferred_name", val, source="utterance"
                    )
                    return True
        # home city
        for phrase in ("i live in ", "my home city is "):
            if tl.startswith(phrase):
                val = t[len(phrase) :].strip(" .")
                if val and memory_write_policy.should_write_profile(text, "home_city"):
                    profile_store.upsert(user_id, "home_city", val, source="utterance")
                    return True
    except Exception:
        return updated
    return updated


# ---------------------------------------------------------------------------
# Main entry‑point
# ---------------------------------------------------------------------------
async def route_prompt(
    prompt: str,
    user_id: str,
    model_override: str | None = None,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
    stream_hook: Callable[[str], Awaitable[None]] | None = None,
    shape: str = "text",
    normalized_from: str | None = None,
    allow_fallback: bool = True,
    **gen_opts: Any,
) -> Any:
    # Generate unique request ID for tracing
    request_id = str(uuid.uuid4())[:8]

    # Step 2: Log model routing inputs and decisions
    logger.info(
        "🎯 ROUTE_PROMPT: prompt='%s...', model_override=%s, user_id=%s, gen_opts=%s",
        prompt[:50] if len(prompt) > 50 else prompt,
        model_override,
        user_id,
        gen_opts,
        extra={
            "meta": {
                "prompt_length": len(prompt),
                "model_override": model_override,
                "user_id": user_id,
                "gen_opts_keys": list(gen_opts.keys()) if gen_opts else [],
            }
        },
    )

    # Detect intent and count tokens
    norm_prompt = prompt.lower().strip()
    intent, priority = detect_intent(prompt)
    tokens = count_tokens(prompt)

    # Check for debug mode
    debug_route = os.getenv("DEBUG_MODEL_ROUTING", "0").lower() in {"1", "true", "yes"}

    # Early cache lookup short-circuit
    cached_answer = lookup_cached_answer(norm_prompt)
    if cached_answer is not None:
        # Record cache hit in metrics
        from .analytics import record_cache_lookup

        await record_cache_lookup(hit=True)

        logger.info(
            "💾 CACHE HIT: Returning cached answer for prompt",
            extra={
                "meta": {
                    "request_id": request_id,
                    "prompt_length": len(prompt),
                    "cached_answer_length": len(cached_answer),
                    "user_id": user_id,
                }
            },
        )

        # Log golden trace for cache hit
        cache_routing_decision = RoutingDecision(
            vendor="cache",
            model="cache",
            reason="cache_hit",
            keyword_hit=None,
            stream=bool(stream_cb),
            allow_fallback=allow_fallback,
            request_id=request_id,
        )
        _log_golden_trace(
            request_id=request_id,
            user_id=user_id,
            path="/v1/ask",
            shape=shape,
            normalized_from=normalized_from,
            override_in=model_override,
            intent=intent,
            tokens_est=tokens,
            routing_decision=cache_routing_decision,
            dry_run=debug_route,
            cb_user_open=False,
            cb_global_open=False,
            latency_ms=0,  # Cache hits are instant
            timeout_ms=None,
            fallback_reason=None,
            cache_hit=True,
        )

        return cached_answer
    else:
        # Record cache miss in metrics
        from .analytics import record_cache_lookup

        await record_cache_lookup(hit=False)

    # Determine initial routing decision
    if model_override:
        # Model override path
        mv = model_override.strip()
        logger.info("🔀 MODEL OVERRIDE: %s requested - bypassing skills", mv)

        # Determine vendor from model name
        if mv.startswith("gpt"):
            chosen_vendor = "openai"
            chosen_model = mv
            picker_reason = "explicit_override"
        elif mv.startswith("llama"):
            chosen_vendor = "ollama"
            chosen_model = mv
            picker_reason = "explicit_override"
        else:
            # Unknown model - validate before any imports
            _validate_model_allowlist(mv, "unknown")
            # This should never be reached due to validation above
            raise HTTPException(status_code=400, detail=f"Unknown model '{mv}'")

        # Validate against allow-list before any vendor imports
        _validate_model_allowlist(chosen_model, chosen_vendor)

        # Check vendor health
        if not _check_vendor_health(chosen_vendor):
            if not allow_fallback:
                raise HTTPException(
                    status_code=503,
                    detail={"error": "vendor_unavailable", "vendor": chosen_vendor},
                )
            else:
                # Fallback to opposite vendor
                fallback_vendor = _get_fallback_vendor(chosen_vendor)
                fallback_model = _get_fallback_model(fallback_vendor)
                fallback_reason = f"fallback_{fallback_vendor}"

                # Validate fallback model
                _validate_model_allowlist(fallback_model, fallback_vendor)

                # Check fallback vendor health
                if not _check_vendor_health(fallback_vendor):
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error": "all_vendors_unavailable",
                            "primary": chosen_vendor,
                            "fallback": fallback_vendor,
                        },
                    )

                # Capture original vendor before fallback
                original_vendor = chosen_vendor

                # Use fallback
                chosen_vendor = fallback_vendor
                chosen_model = fallback_model
                picker_reason = fallback_reason

                # Log fallback metrics
                try:
                    from .metrics import ROUTER_FALLBACKS_TOTAL

                    ROUTER_FALLBACKS_TOTAL.labels(
                        from_vendor=original_vendor,
                        to_vendor=chosen_vendor,
                        reason="vendor_unhealthy",
                    ).inc()
                except Exception:
                    pass
    else:
        # Default picker path
        engine, model_name, picker_reason, keyword_hit = pick_model(
            prompt, intent, tokens
        )
        logger.info(
            "🎯 DEFAULT MODEL SELECTION: engine=%s, model=%s, intent=%s, reason=%s",
            engine,
            model_name,
            intent,
            picker_reason,
            extra={
                "meta": {
                    "engine": engine,
                    "model": model_name,
                    "intent": intent,
                    "picker_reason": picker_reason,
                }
            },
        )

        # Determine vendor
        chosen_vendor = "openai" if engine == "gpt" else "ollama"
        chosen_model = model_name

        # Validate against allow-list
        _validate_model_allowlist(chosen_model, chosen_vendor)

        # Check vendor health
        if not _check_vendor_health(chosen_vendor):
            if not allow_fallback:
                raise HTTPException(
                    status_code=503,
                    detail={"error": "vendor_unavailable", "vendor": chosen_vendor},
                )
            else:
                # Fallback to opposite vendor
                fallback_vendor = _get_fallback_vendor(chosen_vendor)
                fallback_model = _get_fallback_model(fallback_vendor)
                fallback_reason = f"fallback_{fallback_vendor}"

                # Validate fallback model
                _validate_model_allowlist(fallback_model, fallback_vendor)

                # Check fallback vendor health
                if not _check_vendor_health(fallback_vendor):
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error": "all_vendors_unavailable",
                            "primary": chosen_vendor,
                            "fallback": fallback_vendor,
                        },
                    )

                # Capture original vendor before fallback
                original_vendor = chosen_vendor

                # Use fallback
                chosen_vendor = fallback_vendor
                chosen_model = fallback_model
                picker_reason = fallback_reason
                keyword_hit = None  # Reset keyword for fallback

                # Log fallback metrics
                try:
                    from .metrics import ROUTER_FALLBACKS_TOTAL

                    ROUTER_FALLBACKS_TOTAL.labels(
                        from_vendor=original_vendor,
                        to_vendor=chosen_vendor,
                        reason="vendor_unhealthy",
                    ).inc()
                except Exception:
                    pass

    # Check circuit breakers
    cb_global_open = llama_circuit_open
    cb_user_open = await _user_circuit_open(user_id) if user_id else False

    # Create routing decision object
    routing_decision = RoutingDecision(
        vendor=chosen_vendor,
        model=chosen_model,
        reason=picker_reason,
        keyword_hit=keyword_hit if "keyword_hit" in locals() else None,
        stream=bool(stream_cb),
        allow_fallback=allow_fallback,
        request_id=request_id,
    )

    # Log the final routing decision
    _log_golden_trace(
        request_id=request_id,
        user_id=user_id,
        path="/v1/ask",
        shape=shape,
        normalized_from=normalized_from,
        override_in=model_override,
        intent=intent,
        tokens_est=tokens,
        routing_decision=routing_decision,
        dry_run=debug_route,
        cb_user_open=cb_user_open,
        cb_global_open=cb_global_open,
        latency_ms=None,
        timeout_ms=None,
        fallback_reason=None,
        cache_hit=False,
    )

    # Execute the chosen vendor
    if debug_route:
        result = _dry(chosen_vendor, chosen_model)
        return result

    if chosen_vendor == "openai":
        # Lazy import OpenAI adapter
        try:
            from .gpt_client import ask_gpt

            result = await ask_gpt(
                prompt,
                model=chosen_model,
                timeout=OPENAI_TIMEOUT_MS / 1000,
                stream_cb=stream_cb,
                routing_decision=routing_decision,
                **gen_opts,
            )
            # Extract just the text from the tuple (text, prompt_tokens, completion_tokens, cost)
            if isinstance(result, tuple) and len(result) >= 1:
                return result[0]
            return result
        except Exception as e:
            # Normalize the error for deterministic fallback policy
            error_type = normalize_error(e)

            # Determine if fallback should be attempted based on error type
            should_fallback = (
                allow_fallback
                and chosen_vendor != _get_fallback_vendor(chosen_vendor)
                and error_type != ErrorType.AUTH_ERROR  # Don't fallback on auth errors
                and error_type
                != ErrorType.PROVIDER_4XX  # Don't fallback on client errors
            )

            if should_fallback:
                # Try fallback
                fallback_vendor = _get_fallback_vendor(chosen_vendor)
                fallback_model = _get_fallback_model(fallback_vendor)

                # Log fallback metrics with specific error type
                try:
                    from .metrics import ROUTER_FALLBACKS_TOTAL

                    ROUTER_FALLBACKS_TOTAL.labels(
                        from_vendor=chosen_vendor,
                        to_vendor=fallback_vendor,
                        reason=error_type.value,
                    ).inc()
                except Exception:
                    pass

                # Try fallback vendor
                if fallback_vendor == "ollama":
                    try:
                        from .llama_integration import ask_llama

                        result = await ask_llama(
                            prompt,
                            model=fallback_model,
                            timeout=OLLAMA_TIMEOUT_MS / 1000,
                            gen_opts=gen_opts,
                            routing_decision=routing_decision,
                        )
                        # Reset user circuit breaker on LLaMA fallback success
                        if user_id:
                            try:
                                await _user_cb_reset(user_id)
                            except Exception:
                                pass
                        return result
                    except Exception:
                        # Record user circuit breaker failure for LLaMA fallback
                        if user_id:
                            try:
                                await _user_cb_record_failure(user_id)
                            except Exception:
                                pass

                # If fallback also fails, raise original error
                raise e
            else:
                # No fallback attempted - raise original error
                raise e

    elif chosen_vendor == "ollama":
        # Lazy import Ollama adapter
        try:
            from .llama_integration import ask_llama

            result = await ask_llama(
                prompt,
                model=chosen_model,
                timeout=OLLAMA_TIMEOUT_MS / 1000,
                gen_opts=gen_opts,
                routing_decision=routing_decision,
            )
            # Reset user circuit breaker on LLaMA success
            if user_id:
                try:
                    await _user_cb_reset(user_id)
                except Exception:
                    pass
            return result
        except Exception as e:
            # Normalize the error for deterministic fallback policy
            error_type = normalize_error(e)

            # Record user circuit breaker failure for LLaMA
            if user_id:
                try:
                    await _user_cb_record_failure(user_id)
                except Exception:
                    pass

            # Determine if fallback should be attempted based on error type
            should_fallback = (
                allow_fallback
                and chosen_vendor != _get_fallback_vendor(chosen_vendor)
                and error_type != ErrorType.AUTH_ERROR  # Don't fallback on auth errors
                and error_type
                != ErrorType.PROVIDER_4XX  # Don't fallback on client errors
            )

            if should_fallback:
                # Try fallback
                fallback_vendor = _get_fallback_vendor(chosen_vendor)
                fallback_model = _get_fallback_model(fallback_vendor)

                # Log fallback metrics with specific error type
                try:
                    from .metrics import ROUTER_FALLBACKS_TOTAL

                    ROUTER_FALLBACKS_TOTAL.labels(
                        from_vendor=chosen_vendor,
                        to_vendor=fallback_vendor,
                        reason=error_type.value,
                    ).inc()
                except Exception:
                    pass

                # Try fallback vendor
                if fallback_vendor == "openai":
                    try:
                        from .gpt_client import ask_gpt

                        result = await ask_gpt(
                            prompt,
                            model=fallback_model,
                            timeout=OPENAI_TIMEOUT_MS / 1000,
                            stream_cb=stream_cb,
                            routing_decision=routing_decision,
                            **gen_opts,
                        )
                        # Extract just the text from the tuple
                        if isinstance(result, tuple) and len(result) >= 1:
                            return result[0]
                        return result
                    except Exception:
                        pass

                # If fallback also fails, raise original error
                raise e
            else:
                # No fallback attempted - raise original error
                raise e

    # This should never be reached
    raise HTTPException(status_code=500, detail="No valid vendor found")


# -------------------------------
# Override and helper routines
# -------------------------------
async def _call_gpt_override(
    model,
    prompt,
    norm_prompt,
    session_id,
    user_id,
    rec,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
    rag_client: Any | None = None,
    routing_decision: RoutingDecision | None = None,
):
    built, pt = PromptBuilder.build(
        prompt, session_id=session_id, user_id=user_id, rag_client=rag_client
    )
    try:
        text, pt, ct, cost = await ask_gpt(
            built,
            model,
            SYSTEM_PROMPT,
            stream=bool(stream_cb),
            on_token=stream_cb,
            timeout=OPENAI_TIMEOUT_MS / 1000,
            routing_decision=routing_decision,
        )
    except TypeError:
        text, pt, ct, cost = await ask_gpt(
            built,
            model,
            SYSTEM_PROMPT,
            timeout=OPENAI_TIMEOUT_MS / 1000,
            routing_decision=routing_decision,
        )
    except Exception as e:
        # Preserve provider 4xx as 4xx for transparency; otherwise propagate
        try:
            import httpx as _httpx  # type: ignore

            if isinstance(e, _httpx.HTTPStatusError):
                sc = int(
                    getattr(getattr(e, "response", None), "status_code", 500) or 500
                )
                if 400 <= sc < 500:
                    msg = None
                    try:
                        data = e.response.json()
                        msg = (
                            data.get("error")
                            or data.get("message")
                            or data.get("detail")
                        )
                    except Exception:
                        try:
                            msg = e.response.text
                        except Exception:
                            msg = str(e)
                    from fastapi import HTTPException as _HTTPEx  # type: ignore

                    raise _HTTPEx(status_code=sc, detail=str(msg or "provider_error"))
        except Exception:
            pass
        raise
    if rec:
        rec.engine_used = "gpt"
        rec.model_name = model
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = cost
        rec.response = text
    # Consolidated post-call handling using existing postcall.py module
    postcall_data = PostCallData(
        prompt=prompt,
        response=text,
        vendor="openai",
        model=model,
        prompt_tokens=pt,
        completion_tokens=ct,
        cost_usd=cost,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        metadata={"norm_prompt": norm_prompt, "source": "override"},
    )
    await process_postcall(postcall_data)
    return text


async def _call_llama_override(
    model,
    prompt,
    norm_prompt,
    session_id,
    user_id,
    rec,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
    gen_opts: dict[str, Any] | None = None,
    rag_client: Any | None = None,
    routing_decision: RoutingDecision | None = None,
):
    built, pt = PromptBuilder.build(
        prompt,
        session_id=session_id,
        user_id=user_id,
        rag_client=rag_client,
        **(gen_opts or {}),
    )
    tokens: list[str] = []
    logger.debug(
        "LLaMA override opts: temperature=%s top_p=%s",
        (gen_opts or {}).get("temperature"),
        (gen_opts or {}).get("top_p"),
    )
    try:
        try:
            agen = ask_llama(
                built,
                model,
                timeout=OLLAMA_TIMEOUT_MS / 1000,
                routing_decision=routing_decision,
                **(gen_opts or {}),
            )
        except TypeError:
            agen = ask_llama(
                built,
                model,
                timeout=OLLAMA_TIMEOUT_MS / 1000,
                gen_opts=gen_opts,
                routing_decision=routing_decision,
            )
        async for tok in agen:
            tokens.append(tok)
            if stream_cb:
                await stream_cb(tok)
    except Exception:
        raise HTTPException(status_code=503, detail="LLaMA backend unavailable")
    result_text = "".join(tokens).strip()
    if not result_text or _low_conf(result_text):
        raise HTTPException(status_code=503, detail="Low-confidence LLaMA response")
    if rec:
        rec.engine_used = "llama"
        rec.model_name = model
        rec.prompt_tokens = pt
        rec.response = result_text
    # Consolidated post-call handling using existing postcall.py module
    # Note: _call_llama_override actually uses GPT backend, so vendor is "openai"
    postcall_data = PostCallData(
        prompt=prompt,
        response=result_text,
        vendor="openai",  # LLaMA override uses GPT backend
        model=model,
        prompt_tokens=pt if "pt" in locals() else 0,
        completion_tokens=ct if "ct" in locals() else 0,
        cost_usd=cost if "cost" in locals() else 0.0,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        metadata={"norm_prompt": norm_prompt, "source": "override"},
    )
    await process_postcall(postcall_data)
    return result_text


async def _call_gpt(
    *,
    prompt: str,
    built_prompt: str,
    model: str,
    rec,
    norm_prompt: str,
    session_id: str,
    user_id: str,
    ptoks: int,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
    fallback: bool = False,
    routing_decision: RoutingDecision,
):
    logger.info(
        "🤖 CALLING GPT: model=%s, prompt_len=%d",
        model,
        len(prompt),
        extra={
            "meta": {
                "model": model,
                "prompt_length": len(prompt),
            }
        },
    )

    logger.debug(
        "_call_gpt start prompt=%r model=%s user_id=%s", prompt, model, user_id
    )

    # Call GPT and handle exceptions
    try:
        text, pt, ct, cost = await ask_gpt(
            built_prompt,
            model,
            SYSTEM_PROMPT,
            stream=bool(stream_cb),
            on_token=stream_cb,
            timeout=OPENAI_TIMEOUT_MS / 1000,
            routing_decision=routing_decision,
        )
    except TypeError:
        text, pt, ct, cost = await ask_gpt(
            built_prompt,
            model,
            SYSTEM_PROMPT,
            timeout=OPENAI_TIMEOUT_MS / 1000,
            routing_decision=routing_decision,
        )
    except Exception:
        # Record failure for circuit breaker
        _openai_record_failure()
        _mark_openai_unhealthy()
        logger.exception("_call_gpt failure")
        raise

    # Record successful response and reset circuit breaker
    _openai_reset_failures()

    # Record/memory/cache block - always runs on success
    if rec:
        rec.engine_used = "gpt"
        rec.model_name = model
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = cost
        rec.response = text

    # Consolidated post-call handling using existing postcall.py module
    postcall_data = PostCallData(
        prompt=prompt,
        response=text,
        vendor="openai",
        model=model,
        prompt_tokens=pt,
        completion_tokens=ct,
        cost_usd=cost,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        metadata={"norm_prompt": norm_prompt, "source": "router"},
    )
    await process_postcall(postcall_data)

    logger.debug("_call_gpt result model=%s result=%s", model, text)
    return await _finalise("gpt", prompt, text, rec, fallback=fallback)


async def _call_llama(
    *,
    prompt: str,
    built_prompt: str,
    model: str,
    rec,
    norm_prompt: str,
    session_id: str,
    user_id: str,
    ptoks: int,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
    gen_opts: dict[str, Any] | None = None,
    routing_decision: RoutingDecision,
):
    logger.info(
        "🤖 CALLING LLAMA: model=%s, prompt_len=%d",
        model,
        len(prompt),
        extra={
            "meta": {
                "model": model,
                "prompt_length": len(prompt),
            }
        },
    )
    logger.debug(
        "_call_llama start prompt=%r model=%s user_id=%s", prompt, model, user_id
    )
    tokens: list[str] = []
    logger.debug(
        "LLaMA opts: temperature=%s top_p=%s",
        (gen_opts or {}).get("temperature"),
        (gen_opts or {}).get("top_p"),
    )

    # Call LLaMA and handle exceptions
    try:
        try:
            result = ask_llama(
                built_prompt,
                model,
                timeout=OLLAMA_TIMEOUT_MS / 1000,
                routing_decision=routing_decision,
                **(gen_opts or {}),
            )
        except TypeError:
            result = ask_llama(
                built_prompt,
                model,
                timeout=OLLAMA_TIMEOUT_MS / 1000,
                gen_opts=gen_opts,
                routing_decision=routing_decision,
            )

        if inspect.isasyncgen(result):
            async for tok in result:
                tokens.append(tok)
                if stream_cb:
                    await stream_cb(tok)
            result_text = "".join(tokens).strip()
        else:
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict) and result.get("error"):
                raise RuntimeError(str(result.get("error")))
            result_text = (result or "").strip()

    except Exception as e:
        _mark_llama_unhealthy()

        # Normalize error for deterministic fallback policy
        error_type = normalize_error(e)

        # Only fallback for retryable errors
        should_fallback = error_type in (
            ErrorType.PROVIDER_5XX,
            ErrorType.NETWORK_TIMEOUT,
        )

        if should_fallback:
            fallback_model = os.getenv("OPENAI_MODEL", "gpt-4o")
            try:
                text = await _call_gpt(
                    prompt=prompt,
                    built_prompt=built_prompt,
                    model=fallback_model,
                    rec=rec,
                    norm_prompt=norm_prompt,
                    session_id=session_id,
                    user_id=user_id,
                    ptoks=ptoks,
                    stream_cb=stream_cb,
                    fallback=True,
                )
                logger.debug(
                    "_call_llama fallback result model=%s result=%s",
                    fallback_model,
                    text,
                )
                # Tag fallback for response headers via telemetry record
                try:
                    if rec:
                        rec.engine_used = "gpt"
                        rec.route_reason = (
                            rec.route_reason or ""
                        ) + "|fallback_from_llama"
                except Exception:
                    pass
                return text
            except Exception:
                logger.exception("_call_llama fallback to GPT failed")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="GPT backend unavailable",
                )
        else:
            # No fallback - re-raise original error
            raise e

    # Check for low confidence response
    if not result_text or _low_conf(result_text):
        # Mark LLaMA unhealthy and fall back to GPT on empty or low-confidence replies
        _mark_llama_unhealthy()
        fallback_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        try:
            text = await _call_gpt(
                prompt=prompt,
                built_prompt=built_prompt,
                model=fallback_model,
                rec=rec,
                norm_prompt=norm_prompt,
                session_id=session_id,
                user_id=user_id,
                ptoks=ptoks,
                stream_cb=stream_cb,
                fallback=True,
            )
            logger.debug(
                "_call_llama low-conf fallback model=%s result=%s",
                fallback_model,
                text,
            )
            try:
                if rec:
                    rec.engine_used = "gpt"
                    rec.route_reason = (rec.route_reason or "") + "|fallback_from_llama"
            except Exception:
                pass
            return text
        except Exception:
            logger.exception("_call_llama low-conf fallback to GPT failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GPT backend unavailable",
            )

    # Record/memory/cache block - always runs on success
    if rec:
        rec.engine_used = "llama"
        rec.model_name = model
        rec.prompt_tokens = ptoks
        rec.response = result_text

    # Consolidated post-call handling using existing postcall.py module
    # Estimate completion tokens since LLaMA doesn't provide structured token counts
    completion_tokens = (
        len(result_text.split()) * 2
    )  # Rough estimate: 2 tokens per word

    postcall_data = PostCallData(
        prompt=prompt,
        response=result_text,
        vendor="ollama",
        model=model,
        prompt_tokens=ptoks,
        completion_tokens=completion_tokens,
        cost_usd=0.0,  # LLaMA doesn't have cost tracking like OpenAI
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        metadata={"norm_prompt": norm_prompt, "source": "router"},
    )
    await process_postcall(postcall_data)

    logger.debug("_call_llama result model=%s result=%s", model, result_text)

    return await _finalise("llama", prompt, result_text, rec)


async def _finalise(
    engine: str, prompt: str, text: str, rec, *, fallback: bool = False
):
    logger.debug("_finalise start engine=%s prompt=%r", engine, prompt)
    try:
        if rec:
            rec.engine_used = engine
            rec.response = text
        await append_history(prompt, engine, text)
        await record(engine, fallback=fallback)
        logger.debug("_finalise result engine=%s text=%s", engine, text)
        return text
    except Exception:
        logger.exception("_finalise failure")
        raise


async def _run_skill(prompt: str, SkillClass, rec):
    skill_resp = await SkillClass().handle(prompt)
    try:
        from . import analytics as _analytics

        await _analytics.record_skill(getattr(SkillClass, "__name__", str(SkillClass)))
    except Exception:
        pass
    return await _finalise("skill", prompt, str(skill_resp), rec)
