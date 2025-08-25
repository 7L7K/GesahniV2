"""
Router Policy Module

This module handles model routing policies including:
- Model picking logic
- Allowlist validation
- Fallback policies
- Circuit breaker checks
"""

import logging
import os
import time
from dataclasses import dataclass

from .intent_detector import detect_intent
from .model_picker import pick_model
from .token_utils import count_tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / Config
# ---------------------------------------------------------------------------

# Import allowlist constants from router.py (single source of truth)
from app.router import ALLOWED_GPT_MODELS, ALLOWED_LLAMA_MODELS

# Environment variables for routing configuration
ROUTER_BUDGET_MS = int(os.getenv("ROUTER_BUDGET_MS", "7000"))
OPENAI_TIMEOUT_MS = int(os.getenv("OPENAI_TIMEOUT_MS", "6000"))
OLLAMA_TIMEOUT_MS = int(os.getenv("OLLAMA_TIMEOUT_MS", "4500"))

# Circuit breaker configuration
OPENAI_HEALTHY = True
openai_failures = 0
openai_circuit_open = False
openai_last_failure_ts = 0.0

# Health check state tracking
openai_health_check_state = {
    "has_ever_succeeded": False,
    "last_success_ts": 0.0,
    "last_check_ts": 0.0,
    "consecutive_failures": 0,
    "next_check_delay": 5.0,  # Start with 5 seconds
    "max_check_delay": 300.0,  # Max 5 minutes
    "success_throttle_delay": 60.0,  # 1 minute after success
}

# ---------------------------------------------------------------------------
# Model Picking Logic
# ---------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    """Represents a routing decision with all relevant metadata."""

    vendor: str
    model: str
    reason: str
    intent: str
    tokens_est: int
    allow_fallback: bool = True
    dry_run: bool = False


def pick_model_with_policy(
    prompt: str,
    model_override: str | None = None,
    allow_fallback: bool = True,
    dry_run: bool = False,
) -> RoutingDecision:
    """
    Pick the best model for a given prompt using policy-based routing.

    Args:
        prompt: The user prompt
        model_override: Optional model override
        allow_fallback: Whether to allow fallback to other models
        dry_run: Whether this is a dry run (no actual call)

    Returns:
        RoutingDecision with vendor, model, and reasoning
    """
    # Detect intent and count tokens
    norm_prompt = prompt.lower().strip()
    intent = detect_intent(norm_prompt)
    tokens_est = count_tokens(prompt)

    # Use model override if provided
    if model_override:
        if model_override.startswith("gpt-"):
            return RoutingDecision(
                vendor="openai",
                model=model_override,
                reason="override",
                intent=intent,
                tokens_est=tokens_est,
                allow_fallback=allow_fallback,
                dry_run=dry_run,
            )
        else:
            return RoutingDecision(
                vendor="ollama",
                model=model_override,
                reason="override",
                intent=intent,
                tokens_est=tokens_est,
                allow_fallback=allow_fallback,
                dry_run=dry_run,
            )

    # Use model picker for automatic selection
    engine, model_name, picker_reason, keyword_hit = pick_model(
        prompt, intent, tokens_est
    )

    # Determine vendor
    chosen_vendor = "openai" if engine == "gpt" else "ollama"

    return RoutingDecision(
        vendor=chosen_vendor,
        model=model_name,
        reason=picker_reason,
        intent=intent,
        tokens_est=tokens_est,
        allow_fallback=allow_fallback,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------------------
# Allowlist Validation
# ---------------------------------------------------------------------------


def validate_model_allowlist(model: str, vendor: str) -> bool:
    """
    Validate that a model is in the allowed list for its vendor.

    Args:
        model: The model name to validate
        vendor: The vendor (openai or ollama)

    Returns:
        True if model is allowed, False otherwise

    Raises:
        ValueError: If vendor is invalid or model is not allowed
    """
    if vendor == "openai":
        allowed_models = ALLOWED_GPT_MODELS
    elif vendor == "ollama":
        allowed_models = ALLOWED_LLAMA_MODELS
    else:
        raise ValueError(f"Invalid vendor: {vendor}")

    if model not in allowed_models:
        logger.warning(f"Model {model} not in {vendor} allowlist: {allowed_models}")
        return False

    return True


def get_fallback_model(vendor: str) -> str:
    """
    Get the fallback model for a given vendor.

    Args:
        vendor: The vendor to get fallback for

    Returns:
        The fallback model name
    """
    if vendor == "openai":
        return os.getenv("OPENAI_MODEL", "gpt-4o")
    elif vendor == "ollama":
        return os.getenv("OLLAMA_MODEL", "llama3:latest")
    else:
        raise ValueError(f"Invalid vendor: {vendor}")


def get_fallback_vendor(vendor: str) -> str:
    """
    Get the opposite vendor for fallback.

    Args:
        vendor: The current vendor

    Returns:
        The fallback vendor
    """
    return "ollama" if vendor == "openai" else "openai"


# ---------------------------------------------------------------------------
# Circuit Breaker Logic
# ---------------------------------------------------------------------------


def check_vendor_health(vendor: str) -> bool:
    """
    Check if a vendor is healthy using eager health gating system.

    Args:
        vendor: The vendor to check

    Returns:
        True if vendor is healthy, False otherwise
    """
    try:
        # Import here to avoid circular imports
        import asyncio

        from .health import _check_vendor_health as eager_check_vendor_health

        # Use the new eager health gating system
        return asyncio.run(
            eager_check_vendor_health(
                vendor, record_failure=False, record_success=False
            )
        )
    except Exception as e:
        logger.error(f"Error in eager health check for vendor {vendor}: {e}")
        # Fallback to legacy health checks
        if vendor == "openai":
            return OPENAI_HEALTHY and not openai_circuit_open
        elif vendor == "ollama":
            # Import here to avoid circular imports
            try:
                from .llama_integration import LLAMA_HEALTHY, llama_circuit_open

                return LLAMA_HEALTHY and not llama_circuit_open
            except ImportError:
                return True  # Assume healthy if module not available
        else:
            return True  # Unknown vendor assumed healthy


def record_vendor_failure(vendor: str) -> None:
    """
    Record a failure for a vendor to update circuit breaker state and eager health gating.

    Args:
        vendor: The vendor that failed
    """
    try:
        # Use the new eager health gating system
        from .health import record_vendor_failure as eager_record_failure

        eager_record_failure(vendor)
    except Exception as e:
        logger.error(
            f"Error recording failure with eager health gating for vendor {vendor}: {e}"
        )

    # Also update legacy circuit breaker for backward compatibility
    global openai_failures, openai_circuit_open, openai_last_failure_ts

    if vendor == "openai":
        now = time.monotonic()
        if now - openai_last_failure_ts > 60:
            openai_failures = 1
        else:
            openai_failures += 1
        openai_last_failure_ts = now
        if openai_failures >= 3:
            openai_circuit_open = True
            logger.warning(
                "OpenAI circuit breaker opened after %d failures", openai_failures
            )
    elif vendor == "ollama":
        # Import here to avoid circular imports
        try:
            from .llama_integration import _record_failure

            _record_failure()
        except ImportError:
            pass  # Ignore if module not available


def reset_vendor_failures(vendor: str) -> None:
    """
    Reset failure count for a vendor.

    Args:
        vendor: The vendor to reset
    """
    global openai_failures, openai_circuit_open

    if vendor == "openai":
        openai_failures = 0
        openai_circuit_open = False
    elif vendor == "ollama":
        # Import here to avoid circular imports
        try:
            from .llama_integration import _reset_failures

            _reset_failures()
        except ImportError:
            pass  # Ignore if module not available


# ---------------------------------------------------------------------------
# Fallback Policy
# ---------------------------------------------------------------------------


def should_fallback(decision: RoutingDecision) -> bool:
    """
    Determine if fallback should be attempted based on policy.

    Args:
        decision: The current routing decision

    Returns:
        True if fallback should be attempted
    """
    if not decision.allow_fallback:
        return False

    # Check if primary vendor is unhealthy
    if not check_vendor_health(decision.vendor):
        return True

    # Check if model is in allowlist
    if not validate_model_allowlist(decision.model, decision.vendor):
        return True

    return False


# Per-user LLM fallback rate limiter (rolling window)
_LLM_FALLBACK_WINDOW_S = int(os.getenv("LLM_FALLBACK_WINDOW_S", "60"))
_llm_last_call: dict[str, float] = {}


def can_user_call_llm(user_id: str | None) -> bool:
    if user_id is None:
        # treat anonymous as more restricted
        return False
    now = time.time()
    last = _llm_last_call.get(user_id)
    if last and (now - last) < _LLM_FALLBACK_WINDOW_S:
        return False
    _llm_last_call[user_id] = now
    return True


def get_fallback_decision(decision: RoutingDecision) -> RoutingDecision:
    """
    Get the fallback routing decision.

    Args:
        decision: The original routing decision

    Returns:
        A new RoutingDecision for the fallback
    """
    fallback_vendor = get_fallback_vendor(decision.vendor)
    fallback_model = get_fallback_model(fallback_vendor)

    return RoutingDecision(
        vendor=fallback_vendor,
        model=fallback_model,
        reason=f"fallback_{fallback_vendor}",
        intent=decision.intent,
        tokens_est=decision.tokens_est,
        allow_fallback=False,  # Don't allow double fallback
        dry_run=decision.dry_run,
    )


# ---------------------------------------------------------------------------
# Health Check Management
# ---------------------------------------------------------------------------


async def check_openai_health() -> None:
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
        from .gpt_client import ask_gpt

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
        # Failure - update state
        openai_health_check_state["consecutive_failures"] += 1

        # Exponential backoff
        openai_health_check_state["next_check_delay"] = min(
            openai_health_check_state["next_check_delay"] * 2,
            openai_health_check_state["max_check_delay"],
        )

        if openai_health_check_state["has_ever_succeeded"]:
            logger.warning("OpenAI health check failed after previous success: %s", e)
        else:
            logger.warning(
                "OpenAI health check failed (attempt %d, next check in %.1fs): %s",
                openai_health_check_state["consecutive_failures"],
                openai_health_check_state["next_check_delay"],
                e,
            )


def reset_openai_failures() -> None:
    """Reset OpenAI circuit breaker failure counters."""
    global openai_failures, openai_circuit_open
    openai_failures = 0
    openai_circuit_open = False


def mark_openai_unhealthy() -> None:
    """Flip the shared health flag so the picker knows OpenAI is down."""
    global OPENAI_HEALTHY
    OPENAI_HEALTHY = False
