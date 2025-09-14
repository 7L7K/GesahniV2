"""Vendor health check helpers.

This module contains small, test-friendly helpers used during application
startup to verify optional external services (OpenAI and Ollama). Checks are
gated by the environment to avoid slow or brittle CI runs. The functions here
are intentionally lightweight: they return structured dictionaries describing
the observed status and avoid raising for expected misconfiguration.

Environment flags:
- ``STARTUP_VENDOR_PINGS``: enable/disable vendor pings (default: disabled).
- ``STARTUP_CHECK_TIMEOUT``: per-vendor timeout in seconds (default: 10).
- ``OPENAI_API_KEY``: required for OpenAI health check when pings are enabled.
- ``OLLAMA_URL`` / ``LLAMA_URL``: required for Ollama health check.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


async def check_vendor_health_gated(
    vendor: str, *, timeout: int = 10
) -> dict[str, str]:
    """Perform a gated health check for the named vendor.

    The check runs only when ``STARTUP_VENDOR_PINGS`` is truthy. Returns a dict
    describing the outcome. Keys commonly returned:

    - ``status``: one of ``healthy``, ``skipped``, ``missing_config``,
      ``invalid_config``, ``unhealthy``, ``disabled``, ``unknown_vendor``,
      or ``error``.
    - Additional keys vary by vendor: ``model``, ``url``, ``reason``, ``error``.

    Args:
        vendor: Vendor short name, e.g., ``"openai"`` or ``"ollama"``.
        timeout: Timeout in seconds for the vendor probe.

    Returns:
        A dictionary with at least a ``status`` key describing the result.
    """
    vendor_pings_enabled = os.getenv("STARTUP_VENDOR_PINGS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if not vendor_pings_enabled:
        logger.debug("Startup vendor pings disabled; skipping %s health check", vendor)
        return {"status": "skipped", "reason": "pings_disabled"}

    try:
        if vendor == "openai":
            return await _check_openai_health(timeout)
        elif vendor == "ollama":
            return await _check_ollama_health(timeout)
        else:
            logger.warning("Unknown vendor for health check: %s", vendor)
            return {"status": "unknown_vendor", "vendor": vendor}
    except Exception as e:
        logger.error("Vendor health check failed for %s: %s", vendor, e)
        return {"status": "error", "error": str(e), "vendor": vendor}


async def _check_openai_health(timeout: int) -> dict[str, str]:
    """Lightweight OpenAI health probe.

    Behavior:
    - If ``OPENAI_API_KEY`` is missing, returns ``{"status": "missing_config"}``.
    - Performs a tiny ping using ``app.gpt_client.ask_gpt`` to exercise network
      connectivity and API key validity when possible.
    - Classifies common failure modes (network, unauthorized, model access,
      rate-limit) into the ``reason`` field to aid diagnostics.

    This function never raises on expected misconfiguration; it returns a
    descriptive dict instead so startup can continue gracefully.
    """
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {"status": "missing_config", "config": "OPENAI_API_KEY"}

        if not api_key.startswith("sk-"):
            return {"status": "invalid_config", "config": "OPENAI_API_KEY"}

        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url and not base_url.endswith("/v1"):
            logger.warning("OPENAI_BASE_URL should end with /v1, got: %s", base_url)

        try:
            from app.gpt_client import ask_gpt
            from app.router import RoutingDecision

            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            routing_decision = RoutingDecision(
                vendor="openai",
                model=model,
                reason="startup_health_check",
                keyword_hit=None,
                stream=False,
                allow_fallback=False,
                request_id="startup_check",
            )

            # Minimal prompt to verify connectivity and auth
            tiny_prompt = "ping"
            system_prompt = "You are a helpful assistant."

            text, *_ = await ask_gpt(
                tiny_prompt,
                model=model,
                system=system_prompt,
                timeout=timeout,
                routing_decision=routing_decision,
            )

            if text and len(text.strip()) > 0:
                logger.info(
                    "vendor_health vendor=openai ok=true reason=successful_ping model=%s",
                    model,
                )
                return {
                    "status": "healthy",
                    "model": model,
                    "response_length": len(text.strip()),
                }
            else:
                return {
                    "status": "unhealthy",
                    "reason": "empty_response",
                    "model": model,
                }

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "connect" in error_msg.lower():
                reason = "network_connectivity_error"
            elif "unauthorized" in error_msg.lower() or "invalid" in error_msg.lower():
                reason = "api_key_invalid"
            elif "not found" in error_msg.lower() or "model" in error_msg.lower():
                reason = "model_access_error"
            elif "rate limit" in error_msg.lower():
                reason = "rate_limit_error"
            else:
                reason = f"{error_type}_{error_msg[:50].replace(' ', '_')}"

            logger.error(
                "vendor_health vendor=openai ok=false reason=%s error_type=%s error_msg=%s",
                reason,
                error_type,
                error_msg,
            )
            return {"status": "unhealthy", "reason": reason, "error_type": error_type}

    except Exception as e:
        logger.error("OpenAI startup health check failed: %s", e)
        return {"status": "error", "error": str(e)}


async def _check_ollama_health(timeout: int) -> dict[str, str]:
    """Lightweight Ollama/LLaMA health probe.

    - Returns ``disabled`` if LLAMA_ENABLED is explicitly turned off.
    - Returns ``missing_config`` if no Ollama URL is present and LLAMA_ENABLED is
      not explicitly true.
    - Otherwise delegates to the LLaMA integration health check.
    """
    try:
        llama_enabled = (os.getenv("LLAMA_ENABLED") or "").strip().lower()
        if llama_enabled in {"0", "false", "no", "off"}:
            return {"status": "disabled", "reason": "LLAMA_ENABLED=false"}

        ollama_url = os.getenv("OLLAMA_URL") or os.getenv("LLAMA_URL")
        if not ollama_url and llama_enabled not in {"1", "true", "yes", "on"}:
            return {"status": "missing_config", "config": "OLLAMA_URL"}

        from app.llama_integration import _check_and_set_flag

        # Delegate to integration which performs the concrete probe
        await _check_and_set_flag()

        return {"status": "healthy", "url": ollama_url}

    except Exception as e:
        logger.error("Ollama startup health check failed: %s", e)
        return {"status": "error", "error": str(e)}


def should_perform_startup_checks() -> bool:
    """Return True when startup vendor pings are enabled by environment.

    This helper centralizes the gating flag so callers can reason about costs
    of enabling pings in CI or developer workflows.
    """
    return os.getenv("STARTUP_VENDOR_PINGS", "0").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_startup_check_timeout() -> int:
    """Return the configured timeout (seconds) for startup vendor checks.

    Falls back to 10 seconds on malformed values.
    """
    try:
        return int(os.getenv("STARTUP_CHECK_TIMEOUT", "10"))
    except ValueError:
        return 10
