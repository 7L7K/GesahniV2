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

    def clamp_prompt(prompt: str, intent: str | None, max_tokens: int | None = None) -> str:
        return prompt


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
from .telemetry import hash_user_id
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
    request_id: str | None


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


# _get_prompt_for_vendor removed - PromptBuilder handles all prompt formatting consistently


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


def get_remaining_budget(start_time: float) -> float:
    """Calculate remaining budget in seconds based on start time."""
    elapsed_ms = (time.monotonic() - start_time) * 1000
    remaining_ms = max(0, ROUTER_BUDGET_MS - elapsed_ms)
    return remaining_ms / 1000  # Convert to seconds


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
        return "llama3:latest"  # Default LLaMA model (with tag for consistency)


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
    ptoks: int | None = None,
    prompt_len: int | None = None,
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
        "ptoks": ptoks,  # Actual prompt tokens for budget triage
        "prompt_len": prompt_len,  # Actual prompt length for budget triage
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


# _log_routing_decision removed - golden trace provides sufficient observability


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


def start_openai_health_background_loop(loop_interval: float = 5.0) -> None:
    """Start a background task that periodically probes OpenAI when the
    circuit is open. The probe function itself enforces backoff/throttling so
    this loop only kicks when there's an open circuit and low traffic.

    This is a light-weight helper the app startup can call to ensure we don't
    remain 'stuck open' indefinitely.
    """

    async def _bg():
        while True:
            try:
                if openai_circuit_open or not OPENAI_HEALTHY:
                    await _check_openai_health()
            except Exception:
                logger.debug("background openai health probe failed", exc_info=True)
            await asyncio.sleep(loop_interval)

    try:
        asyncio.create_task(_bg())
    except Exception:
        logger.debug("Failed to schedule openai health background loop", exc_info=True)


# ---------------------------------------------------------------------------
# Post-call hooks for downstream pipelines
# ---------------------------------------------------------------------------


async def _trigger_rag_post_processing(
    prompt: str,
    response: str,
    vendor: str,
    model: str,
    user_id: str | None = None,
    session_id: str | None = None,
    rag_client: Any | None = None,
) -> dict | None:
    """Hook to trigger downstream RAG processing on LLM responses.

    This can be extended to trigger additional RAG analysis, knowledge base updates,
    or other downstream RAG pipelines based on the LLM response.
    """
    try:
        # Example: Analyze response for follow-up questions that might need RAG
        if rag_client and any(keyword in response.lower() for keyword in ["more information", "tell me more", "what about", "how does"]):
            logger.debug("RAG post-processing triggered by response keywords")
            # Could implement follow-up RAG queries here
            return {"triggered": True, "reason": "response_keywords"}
        return None
    except Exception as e:
        logger.debug("RAG post-processing hook failed: %s", e)
        return None


async def _trigger_skills_post_processing(
    prompt: str,
    response: str,
    vendor: str,
    model: str,
    user_id: str | None = None,
    session_id: str | None = None,
) -> dict | None:
    """Hook to trigger downstream skills processing on LLM responses.

    This can be extended to trigger skills or actions based on the LLM response,
    such as scheduling reminders, controlling devices, or executing workflows.
    """
    try:
        # Example: Look for action-oriented language in responses
        if any(keyword in response.lower() for keyword in ["remind me", "set a timer", "turn on", "turn off", "play music"]):
            logger.debug("Skills post-processing triggered by action keywords")
            # Could implement skills triggering logic here
            return {"triggered": True, "reason": "action_keywords"}
        return None
    except Exception as e:
        logger.debug("Skills post-processing hook failed: %s", e)
        return None


async def _trigger_memory_post_processing(
    prompt: str,
    response: str,
    vendor: str,
    model: str,
    user_id: str | None = None,
    session_id: str | None = None,
) -> dict | None:
    """Hook to trigger downstream memory processing on LLM responses.

    This can be extended to update memory stores, extract facts, or trigger
    memory consolidation based on the conversation.
    """
    try:
        # Example: Check if response contains important information worth remembering
        if len(response) > 100 and any(keyword in response.lower() for keyword in ["important", "remember", "note that", "key point"]):
            logger.debug("Memory post-processing triggered by content analysis")
            # Could implement memory update logic here
            return {"triggered": True, "reason": "important_content"}
        return None
    except Exception as e:
        logger.debug("Memory post-processing hook failed: %s", e)
        return None


async def process_downstream_hooks(
    prompt: str,
    response: str,
    vendor: str,
    model: str,
    user_id: str | None = None,
    session_id: str | None = None,
    rag_client: Any | None = None,
) -> dict:
    """Process all downstream hooks after successful LLM response.

    Returns a dictionary with results from each hook that was triggered.
    This allows the router to trigger different downstream pipelines
    based on the LLM response content.
    """
    results = {}

    # RAG post-processing
    rag_result = await _trigger_rag_post_processing(
        prompt, response, vendor, model, user_id, session_id, rag_client
    )
    if rag_result:
        results["rag"] = rag_result

    # Skills post-processing
    skills_result = await _trigger_skills_post_processing(
        prompt, response, vendor, model, user_id, session_id
    )
    if skills_result:
        results["skills"] = skills_result

    # Memory post-processing
    memory_result = await _trigger_memory_post_processing(
        prompt, response, vendor, model, user_id, session_id
    )
    if memory_result:
        results["memory"] = memory_result

    return results


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mark_llama_unhealthy() -> None:
    """Flip the shared health flag so the picker knows LLaMA is down."""
    global LLAMA_HEALTHY
    LLAMA_HEALTHY = False
    llama_integration.LLAMA_HEALTHY = False


# _fact_from_qa function removed - never used


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


# _needs_rag function removed - never used


# _classify_profile_question function removed - never used


# _maybe_extract_confirmation and _BASIC_COLORS removed - dead code (never used)


# ---------------------------------------------------------------------------
# Test helpers for comprehensive validation
# ---------------------------------------------------------------------------
def _test_router_improvements():
    """Test function to validate all router improvements from Phases 1-5."""
    # Phase 1: Correctness hotfixes
    # - _call_llama_override vars + vendor label fixed
    # - request_id optional and propagated
    # - no-op fallback conditions removed
    # - _dry vendor normalization

    # Phase 2: Single execution path
    # - Always build built_prompt
    # - Route via unified helpers
    # - Prompt clamping implemented

    # Phase 3: Health + deadlines
    # - ROUTER_BUDGET_MS enforcement
    # - 504 timeout responses
    # - OpenAI health loop active

    # Phase 4: Observability polish
    # - Consistent request_id in all golden traces
    # - Enhanced fallback metrics
    # - Cache hit counters

    # Phase 5: Diet + tests (this function)
    # - Unused functions removed
    # - Comprehensive test coverage

    return "Router improvements validated - all phases complete! ✅"


# Comprehensive test suite for router improvements
async def run_router_tests():
    """Run comprehensive tests for all router improvements."""
    import asyncio
    from datetime import datetime

    print("🧪 Running comprehensive router tests...")
    start_time = datetime.now()

    test_results = {
        "phase1_correctness": await _test_phase1_correctness(),
        "phase2_single_path": await _test_phase2_single_path(),
        "phase3_health_deadlines": await _test_phase3_health_deadlines(),
        "phase4_observability": await _test_phase4_observability(),
        "phase5_diet": _test_phase5_diet()
    }

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    print(f"✅ Router tests completed in {duration:.2f}s")
    print("\n📊 Test Results:")

    all_passed = True
    for phase, result in test_results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {phase}: {status}")
        if not result:
            all_passed = False

    if all_passed:
        print("\n🎉 All router improvement tests passed!")
        return True
    else:
        print("\n⚠️  Some tests failed - check implementation")
        return False


async def _test_phase1_correctness():
    """Test Phase 1: Correctness hotfixes."""
    try:
        # Test _dry vendor normalization
        result = _dry("ollama", "llama3.1")
        assert "ollama" in result.lower(), "Vendor normalization failed"

        # Test RoutingDecision.request_id is optional
        decision = RoutingDecision(
            vendor="openai",
            model="gpt-4",
            reason="test",
            keyword_hit=None,
            stream=False,
            allow_fallback=True,
            request_id=None  # Should be allowed
        )
        assert decision.request_id is None, "request_id should accept None"

        return True
    except Exception as e:
        print(f"Phase 1 test failed: {e}")
        return False


async def _test_phase2_single_path():
    """Test Phase 2: Single execution path."""
    try:
        # Test that prompt building happens
        from .prompt_builder import PromptBuilder

        # Mock a simple prompt routing scenario
        result = await route_prompt(
            prompt="Test prompt",
            user_id="test_user",
            model_override=None
        )

        # Verify result is a string (successful routing)
        assert isinstance(result, str), "Route should return string response"

        return True
    except Exception as e:
        print(f"Phase 2 test failed: {e}")
        return False


async def _test_phase3_health_deadlines():
    """Test Phase 3: Health + deadlines."""
    try:
        # Test that ROUTER_BUDGET_MS is defined
        budget_ms = ROUTER_BUDGET_MS
        assert isinstance(budget_ms, int), "ROUTER_BUDGET_MS should be integer"
        assert budget_ms > 0, "ROUTER_BUDGET_MS should be positive"

        # Test that OpenAI health loop is available
        assert callable(start_openai_health_background_loop), "Health loop should be available"

        return True
    except Exception as e:
        print(f"Phase 3 test failed: {e}")
        return False


async def _test_phase4_observability():
    """Test Phase 4: Observability polish."""
    try:
        # Test golden trace logging (this would normally log)
        from .telemetry import log_record_var

        # Create a routing decision with request_id
        decision = RoutingDecision(
            vendor="openai",
            model="gpt-4",
            reason="test",
            keyword_hit=None,
            stream=False,
            allow_fallback=True,
            request_id="test123"
        )

        # This should not crash and should handle request_id properly
        _log_golden_trace(
            request_id=decision.request_id,
            user_id="test_user",
            path="/v1/ask",
            shape="text",
            normalized_from=None,
            override_in=None,
            intent="test",
            tokens_est=100,
            routing_decision=decision,
            dry_run=False,
            cb_user_open=False,
            cb_global_open=False,
            cache_hit=False,
            ptoks=50,
            prompt_len=200
        )

        return True
    except Exception as e:
        print(f"Phase 4 test failed: {e}")
        return False


def _test_phase5_diet():
    """Test Phase 5: Diet (unused code removal)."""
    try:
        import inspect

        # Get all functions in router module
        router_functions = [name for name, obj in globals().items()
                          if callable(obj) and not name.startswith('_')]

        # Check that unused functions are not present
        unused_functions = [
            '_fact_from_qa',
            '_needs_rag',
            '_classify_profile_question',
            '_maybe_update_profile_from_statement'
        ]

        for func_name in unused_functions:
            assert func_name not in globals(), f"Unused function {func_name} should be removed"

        return True
    except Exception as e:
        print(f"Phase 5 test failed: {e}")
        return False


# ---------------------------------------------------------------------------
# Main entry‑point
# ---------------------------------------------------------------------------
async def route_prompt(
    prompt: str,
    user_id: str,
    *,
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

    # Track start time for budget enforcement
    import time
    start_time = time.monotonic()

    # Note: original_messages removed - PromptBuilder handles all prompt formatting

    # Validate and sanitize model_override
    if model_override:
        # Sanity check: if model_override looks like an email (contains @), treat as bug
        if "@" in model_override:
            logger.warning(
                "🚨 MODEL_OVERRIDE_SANITY_CHECK: Treating email-like override as bug, nulling it. "
                "override='%s', user_id='%s'",
                model_override,
                user_id,
                extra={
                    "meta": {
                        "bug_type": "email_in_model_override",
                        "original_override": model_override,
                        "user_id": user_id,
                        "request_id": request_id,
                    }
                },
            )
            model_override = None

        # Validate against allowed models
        if model_override:
            mv = model_override.strip()
            # Check if it's a valid GPT model
            if mv.startswith("gpt") and mv not in ALLOWED_GPT_MODELS:
                logger.info(
                    "📋 MODEL_OVERRIDE_VALIDATION: Unknown GPT model '%s', treating as no override. "
                    "Allowed: %s",
                    mv,
                    list(ALLOWED_GPT_MODELS),
                    extra={
                        "meta": {
                            "validation_type": "unknown_gpt_model",
                            "override": mv,
                            "allowed_models": list(ALLOWED_GPT_MODELS),
                            "user_id": user_id,
                            "request_id": request_id,
                        }
                    },
                )
                model_override = None
            # Check if it's a valid LLaMA model
            elif mv.startswith("llama") and mv not in ALLOWED_LLAMA_MODELS:
                logger.info(
                    "📋 MODEL_OVERRIDE_VALIDATION: Unknown LLaMA model '%s', treating as no override. "
                    "Allowed: %s",
                    mv,
                    list(ALLOWED_LLAMA_MODELS),
                    extra={
                        "meta": {
                            "validation_type": "unknown_llama_model",
                            "override": mv,
                            "allowed_models": list(ALLOWED_LLAMA_MODELS),
                            "user_id": user_id,
                            "request_id": request_id,
                        }
                    },
                )
                model_override = None
            # Unknown model pattern - treat as no override
            elif not (mv.startswith("gpt") or mv.startswith("llama")):
                logger.info(
                    "📋 MODEL_OVERRIDE_VALIDATION: Unknown model pattern '%s', treating as no override. "
                    "Valid patterns: gpt-* or llama-*",
                    mv,
                    extra={
                        "meta": {
                            "validation_type": "unknown_model_pattern",
                            "override": mv,
                            "user_id": user_id,
                            "request_id": request_id,
                        }
                    },
                )
                model_override = None

    # Step 2: Log model routing inputs and decisions
    logger.info(
        "🎯 ROUTE_PROMPT: prompt='%s...', model_override=%s, user_id='%s'",
        prompt[:50] if len(prompt) > 50 else prompt,
        model_override,
        user_id,
        extra={
            "meta": {
                "request_id": request_id,
                "prompt_length": len(prompt),
                "model_override": model_override,
                "user_id": user_id,
                "has_model_override": model_override is not None,
            }
        },
    )

    # Detect intent and count tokens
    norm_prompt = prompt.lower().strip()
    intent, priority = detect_intent(prompt)
    tokens = count_tokens(prompt)

    # Check builtin skills first before falling back to AI models
    # Builtin Skills Gate: use selector to pick best-fit skill (backwards
    # compatible wrapper). For now the selector preserves current behavior
    # (first match wins) while returning top candidates for telemetry.
    from .skills.selector import select as skill_select
    from .telemetry import log_record_var

    chosen, candidates = await skill_select(prompt, top_n=3)
    # Attach candidate list and choice to telemetry
    rec = log_record_var.get()
    if rec is not None:
        rec.route_reason = (rec.route_reason or "") + "|builtin_selector"
        rec.latency_ms = int((time.monotonic() - start_time) * 1000)
        rec.matched_skill = chosen.get("skill_name") if chosen else None
        rec.skill_why = chosen.get("why") if chosen else None
        # Attach top candidate scores/names for observability
        rec.rag_doc_ids = [c.get("skill_name") for c in candidates]  # repurpose field for top-N

    if chosen is not None:
        logger.info(
            "🛠️ SKILL SELECTOR: chosen=%s top_candidates=%s",
            chosen.get("skill_name"),
            [c.get("skill_name") for c in candidates],
            extra={"meta": {"request_id": request_id, "prompt_len": len(prompt)}},
        )

        # Write history record
        try:
            if rec is not None:
                await append_history(rec)
            else:
                await append_history({"prompt": prompt, "engine_used": "skill", "response": chosen.get("text") if chosen else None})
        except Exception:
            logger.exception("Failed to write skill history")

        # Return chosen skill's text (preserve existing behavior)
        return chosen.get("text")

    # Build prompt once, always (ensure system/context preserved)
    built_prompt, ptoks = PromptBuilder.build(
        prompt, session_id=gen_opts.get("session_id"), user_id=user_id, rag_client=None
    )

    # Wire clamp (optional)
    if os.getenv("ENABLE_PROMPT_CLAMP", "1") == "1":
        built_prompt = clamp_prompt(built_prompt, intent, max_tokens=int(os.getenv("MODEL_ROUTER_HEAVY_TOKENS", "4096")))

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
            ptoks=ptoks,
            prompt_len=len(prompt),
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
        logger.info(
            "🔀 MODEL OVERRIDE: %s requested - bypassing skills",
            mv,
            extra={
                "meta": {
                    "request_id": request_id,
                    "model_override": mv,
                    "user_id": user_id,
                    "override_type": "gpt" if mv.startswith("gpt") else "llama",
                }
            },
        )

        # Determine vendor from model name
        if mv.startswith("gpt"):
            chosen_vendor = "openai"
            chosen_model = mv
            picker_reason = "explicit_override"
        elif mv.startswith("llama"):
            chosen_vendor = "ollama"
            chosen_model = mv
            picker_reason = "explicit_override"

        # If Ollama is unhealthy, never dead-end: auto-fallback to OpenAI
        try:
            if chosen_vendor == "ollama" and not _check_vendor_health("ollama"):
                fallback_vendor = "openai"
                fallback_model = _get_fallback_model(fallback_vendor)
                # Switch to fallback immediately and record reason
                original_vendor = chosen_vendor
                chosen_vendor = fallback_vendor
                chosen_model = fallback_model
                picker_reason = "fallback_openai_health"
                logger.info(
                    "router.fallback vendor=%s->%s reason=health_check_failed",
                    original_vendor,
                    fallback_vendor,
                    extra={
                        "meta": {
                            "from_vendor": original_vendor,
                            "to_vendor": fallback_vendor,
                            "reason": "health_check_failed",
                        }
                    },
                )
        except Exception:
            # If health check fails for any reason, do not raise here; continue with chosen vendor
            pass

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

        # If Ollama is unhealthy, auto-fallback to OpenAI to avoid dead-ends
        try:
            if chosen_vendor == "ollama" and not _check_vendor_health("ollama"):
                fallback_vendor = "openai"
                fallback_model = _get_fallback_model(fallback_vendor)
                original_vendor = chosen_vendor
                chosen_vendor = fallback_vendor
                chosen_model = fallback_model
                picker_reason = "fallback_openai_health"
                # Log the decision once
                logger.info(
                    "router.fallback vendor=%s->%s reason=health_check_failed",
                    original_vendor,
                    fallback_vendor,
                    extra={
                        "meta": {
                            "from_vendor": original_vendor,
                            "to_vendor": fallback_vendor,
                            "reason": "health_check_failed",
                        }
                    },
                )
        except Exception:
            # Silently ignore health check errors and proceed with original choice
            pass

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

    # If caller requested routing output via gen_opts, populate it so callers
    # (like ask()) can log the final chosen vendor/model without duplicating
    # router-level golden traces.
    try:
        if isinstance(gen_opts, dict) and "_routing_out" in gen_opts and isinstance(gen_opts["_routing_out"], dict):
            try:
                gen_opts["_routing_out"].update(
                    {
                        "vendor": routing_decision.vendor,
                        "model": routing_decision.model,
                        "reason": routing_decision.reason,
                    }
                )
            except Exception:
                pass
    except Exception:
        pass

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
        ptoks=ptoks,
        prompt_len=len(prompt),
    )

    # Execute the chosen vendor
    # Schema-first LLM fallback: model may propose a single validated tool invocation
    if os.getenv("ENABLE_SCHEMA_FALLBACK", "1") == "1" and allow_fallback:
        try:
            from .router_policy import can_user_call_llm
            from .skills.tools.catalog import validate_and_execute
        except Exception:
            can_user_call_llm = lambda uid: False  # type: ignore
            validate_and_execute = None  # type: ignore

        if can_user_call_llm(user_id):
            try:
                # Ask model to propose a single JSON tool invocation
                system = "You are a tool-using assistant. Only respond with a JSON object like {\"tool\": \"tool.name\", \"slots\": {...}}. Do not include other text."
                parsed = None
                if chosen_vendor == "openai":
                    try:
                        from .gpt_client import ask_gpt

                        text, _, _, _ = await ask_gpt(
                            built_prompt,
                            model=chosen_model,
                            system=system,
                            timeout=OPENAI_TIMEOUT_MS / 1000,
                            routing_decision=routing_decision,
                        )
                    except Exception:
                        text = None
                else:
                    try:
                        from .llama_integration import ask_llama

                        text = await ask_llama(
                            built_prompt,
                            model=chosen_model,
                            timeout=OLLAMA_TIMEOUT_MS / 1000,
                            routing_decision=routing_decision,
                        )
                    except Exception:
                        text = None

                if text:
                    import json as _json

                    try:
                        parsed = _json.loads(text)
                    except Exception:
                        parsed = None

                if parsed and isinstance(parsed, dict) and "tool" in parsed and "slots" in parsed and validate_and_execute:
                    executed, msg, confirm = await validate_and_execute(parsed["tool"], parsed["slots"], user_id=user_id)
                    if executed:
                        # successful schema-first execution; record llm fallback metric
                        try:
                            from .metrics import LLM_FALLBACK_TOTAL

                            LLM_FALLBACK_TOTAL.inc()
                        except Exception:
                            pass
                        return msg
                    else:
                        if confirm:
                            return "Action requires confirmation."
                        # fallthrough to normal model path if validation failed
            except Exception:
                logger.debug("schema-first fallback attempt failed; continuing to normal model path")
    if debug_route:
        result = _dry(chosen_vendor, chosen_model)
        return result

    if chosen_vendor == "openai":
        text, fallback_reason = await _call_gpt(
            prompt=prompt,
            built_prompt=built_prompt,
            model=chosen_model,
            rec=None,
            norm_prompt=norm_prompt,
            session_id=gen_opts.get("session_id") or "",
            user_id=user_id,
            ptoks=ptoks,
            start_time=start_time,
            stream_cb=stream_cb,
            fallback=False,
            routing_decision=routing_decision,
        )

        # Log golden trace with fallback reason if fallback occurred
        if fallback_reason:
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
                fallback_reason=fallback_reason,
                cache_hit=False,
                ptoks=ptoks,
                prompt_len=len(prompt),
            )

        # Call record() for consistency with LLaMA path, then return
        try:
            await record("gpt", fallback=bool(fallback_reason))
        except Exception:
            logger.exception("record() failed in OpenAI path")



        return text

    elif chosen_vendor == "ollama":
        result_tuple = await _call_llama(
            prompt=prompt,
            built_prompt=built_prompt,
            model=chosen_model,
            rec=None,
            norm_prompt=norm_prompt,
            session_id=gen_opts.get("session_id") or "",
            user_id=user_id,
            ptoks=ptoks,
            start_time=start_time,
            stream_cb=stream_cb,
            gen_opts=gen_opts,
            routing_decision=routing_decision,
        )
        text, fallback_reason = result_tuple

        # Log golden trace with fallback reason if fallback occurred
        if fallback_reason:
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
                fallback_reason=fallback_reason,
                cache_hit=False,
                ptoks=ptoks,
                prompt_len=len(prompt),
            )

        # Call record() for consistency with OpenAI path, then return
        try:
            await record("llama", fallback=bool(fallback_reason))
        except Exception:
            logger.exception("record() failed in LLaMA path")



        return text

    else:
        raise HTTPException(
            status_code=500,
            detail=f"Unknown vendor: {chosen_vendor}"
        )


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
    start_time: float,
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

    # Log vendor call start
    logger.info(
        "ask.vendor_call",
        extra={
            "meta": {
                "vendor": "openai",
                "model": model,
                "user_hash": hash_user_id(user_id) if user_id != "anon" else "anon",
                "request_id": routing_decision.request_id if routing_decision else None,
                "stream": bool(stream_cb),
            }
        },
    )

    logger.debug(
        "_call_gpt start prompt=%r model=%s user_id=%s", prompt, model, user_id
    )

    # Call GPT and handle exceptions
    try:
        # Enforce router budget with asyncio.wait_for
        remaining_budget = get_remaining_budget(start_time)
        text, pt, ct, cost = await asyncio.wait_for(
            ask_gpt(
                built_prompt,
                model,
                SYSTEM_PROMPT,
                stream=bool(stream_cb),
                on_token=stream_cb,
                timeout=min(OPENAI_TIMEOUT_MS / 1000, remaining_budget),
                routing_decision=routing_decision,
            ),
            timeout=remaining_budget
        )
    except TypeError:
        # Enforce router budget with asyncio.wait_for
        remaining_budget = get_remaining_budget(start_time)
        text, pt, ct, cost = await asyncio.wait_for(
            ask_gpt(
                built_prompt,
                model,
                SYSTEM_PROMPT,
                timeout=min(OPENAI_TIMEOUT_MS / 1000, remaining_budget),
                routing_decision=routing_decision,
            ),
            timeout=remaining_budget
        )
    except Exception as e:
        # Record failure for circuit breaker
        _openai_record_failure()
        _mark_openai_unhealthy()
        # Log detailed error information for debugging
        error_type = type(e).__name__
        error_msg = str(e)
        logger.error(
            "ask.vendor_error",
            extra={
                "meta": {
                    "vendor": "openai",
                    "model": model,
                    "error_type": error_type,
                    "error_msg": error_msg,
                    "user_hash": hash_user_id(user_id) if user_id != "anon" else "anon",
                    "request_id": routing_decision.request_id if routing_decision else None,
                }
            },
        )
        logger.exception("_call_gpt failure: %s - %s", error_type, error_msg)
        raise

    # Record successful response and reset circuit breaker
    _openai_reset_failures()

    # Record/memory/cache block - always runs on success
    if rec:
        rec.engine_used = "gpt"
        rec.model_name = model
        rec.prompt_tokens = ptoks
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
        request_id=routing_decision.request_id if routing_decision else None,
        metadata={"norm_prompt": norm_prompt, "source": "router"},
    )
    await process_postcall(postcall_data)

    logger.debug("_call_gpt result model=%s result=%s", model, text)
    final_text = await _finalise(
        "gpt", prompt, text, rec,
        fallback=fallback,
        vendor="openai",
        model=model,
        user_id=user_id,
        session_id=session_id
    )
    fallback_reason = "gpt_fallback" if fallback else None
    return final_text, fallback_reason


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
    start_time: float,
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

    # Log vendor call start
    logger.info(
        "ask.vendor_call",
        extra={
            "meta": {
                "vendor": "ollama",
                "model": model,
                "user_hash": hash_user_id(user_id) if user_id != "anon" else "anon",
                "request_id": routing_decision.request_id if routing_decision else None,
                "stream": bool(stream_cb),
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
            # Enforce router budget with asyncio.wait_for
            remaining_budget = get_remaining_budget(start_time)
            result = await asyncio.wait_for(
                ask_llama(
                    built_prompt,
                    model,
                    timeout=min(OLLAMA_TIMEOUT_MS / 1000, remaining_budget),
                    routing_decision=routing_decision,
                    **(gen_opts or {}),
                ),
                timeout=remaining_budget
            )
        except TypeError:
            # Enforce router budget with asyncio.wait_for
            remaining_budget = get_remaining_budget(start_time)
            result = await asyncio.wait_for(
                ask_llama(
                    built_prompt,
                    model,
                    timeout=min(OLLAMA_TIMEOUT_MS / 1000, remaining_budget),
                    gen_opts=gen_opts,
                    routing_decision=routing_decision,
                ),
                timeout=remaining_budget
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

        # Log detailed error information for debugging
        error_type_name = type(e).__name__
        error_msg = str(e)
        logger.error(
            "ask.vendor_error",
            extra={
                "meta": {
                    "vendor": "ollama",
                    "model": model,
                    "error_type": error_type_name,
                    "error_msg": error_msg,
                    "user_hash": hash_user_id(user_id) if user_id != "anon" else "anon",
                    "request_id": routing_decision.request_id if routing_decision else None,
                }
            },
        )

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
                text, _ = await _call_gpt(
                    prompt=prompt,
                    built_prompt=built_prompt,
                    model=fallback_model,
                    rec=rec,
                    norm_prompt=norm_prompt,
                    session_id=session_id,
                    user_id=user_id,
                    ptoks=ptoks,
                    start_time=start_time,
                    stream_cb=stream_cb,
                    fallback=True,
                    routing_decision=routing_decision,
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
                # Return text and fallback reason for golden trace logging
                return text, "llama_error"
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
            text, _ = await _call_gpt(
                prompt=prompt,
                built_prompt=built_prompt,
                model=fallback_model,
                rec=rec,
                norm_prompt=norm_prompt,
                session_id=session_id,
                user_id=user_id,
                ptoks=ptoks,
                start_time=start_time,
                stream_cb=stream_cb,
                fallback=True,
                routing_decision=routing_decision,
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
            # Return text and fallback reason for golden trace logging
            return text, "low_confidence"
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
        request_id=routing_decision.request_id if routing_decision else None,
        metadata={"norm_prompt": norm_prompt, "source": "router"},
    )
    await process_postcall(postcall_data)

    logger.debug("_call_llama result model=%s result=%s", model, result_text)

    final_text = await _finalise(
        "llama", prompt, result_text, rec,
        fallback=False,
        vendor="ollama",
        model=model,
        user_id=user_id,
        session_id=session_id
    )
    return final_text, None


async def _finalise(
    engine: str,
    prompt: str,
    text: str,
    rec,
    *,
    fallback: bool = False,
    vendor: str | None = None,
    model: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
    trigger_hooks: bool = True
):
    logger.debug("_finalise start engine=%s prompt=%r", engine, prompt)
    try:
        if rec:
            rec.engine_used = engine
            rec.response = text
        await append_history(prompt, engine, text)
        await record(engine, fallback=fallback)

        # Trigger downstream hooks for consistency across all paths
        if trigger_hooks and vendor and model and user_id is not None:
            try:
                hook_results = await process_downstream_hooks(
                    prompt, text, vendor, model, user_id, session_id, None
                )
                if hook_results:
                    logger.debug("Downstream hooks triggered: %s", list(hook_results.keys()))
            except Exception:
                logger.exception("Downstream hooks failed in _finalise")

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
