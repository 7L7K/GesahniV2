"""
Startup utilities for vendor health checks and initialization.

This module handles vendor ping gating during application startup,
providing timeouts and proper error handling for external service checks.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def check_vendor_health_gated(vendor: str, *, timeout: int = 10) -> dict[str, str]:
    """
    Check vendor health with gating based on STARTUP_VENDOR_PINGS environment variable.

    Args:
        vendor: The vendor name to check ('openai', 'ollama', etc.)
        timeout: Timeout in seconds for the health check

    Returns:
        Dictionary with status and any error information
    """
    # Check if vendor pings are enabled
    vendor_pings_enabled = (
        os.getenv("STARTUP_VENDOR_PINGS", "0").strip().lower() in {"1", "true", "yes", "on"}
    )

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
    """Check OpenAI API health during startup."""
    try:
        # Check if API key is configured
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return {"status": "missing_config", "config": "OPENAI_API_KEY"}

        # Validate API key format (basic check)
        if not api_key.startswith("sk-"):
            return {"status": "invalid_config", "config": "OPENAI_API_KEY"}

        # Check base URL configuration
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url and not base_url.endswith("/v1"):
            logger.warning("OPENAI_BASE_URL should end with /v1, got: %s", base_url)

        # Perform tiny ping with 5-token prompt
        try:
            from .gpt_client import ask_gpt
            from .router import RoutingDecision

            model = os.getenv("OPENAI_MODEL", "gpt-4o")
            routing_decision = RoutingDecision(
                vendor="openai",
                model=model,
                reason="startup_health_check",
                keyword_hit=None,
                stream=False,
                allow_fallback=False,
                request_id="startup_check"
            )

            # Use a very small prompt to minimize costs
            tiny_prompt = "ping"
            system_prompt = "You are a helpful assistant."

            # This will test: network connectivity, API key validity, model accessibility
            text, _, _, _ = await ask_gpt(
                tiny_prompt,
                model=model,
                system=system_prompt,
                timeout=timeout,
                routing_decision=routing_decision
            )

            # Check if we got a reasonable response
            if text and len(text.strip()) > 0:
                logger.info("vendor_health vendor=openai ok=true reason=successful_ping model=%s", model)
                return {"status": "healthy", "model": model, "response_length": len(text.strip())}
            else:
                return {"status": "unhealthy", "reason": "empty_response", "model": model}

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)

            # Classify common error types
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

            logger.error("vendor_health vendor=openai ok=false reason=%s error_type=%s error_msg=%s",
                        reason, error_type, error_msg)
            return {"status": "unhealthy", "reason": reason, "error_type": error_type}

    except Exception as e:
        logger.error("OpenAI startup health check failed: %s", e)
        return {"status": "error", "error": str(e)}


async def _check_ollama_health(timeout: int) -> dict[str, str]:
    """Check Ollama/LLaMA health during startup."""
    try:
        # Check if LLaMA is explicitly disabled
        llama_enabled = (os.getenv("LLAMA_ENABLED") or "").strip().lower()
        if llama_enabled in {"0", "false", "no", "off"}:
            return {"status": "disabled", "reason": "LLAMA_ENABLED=false"}

        # Check if Ollama URL is configured
        ollama_url = os.getenv("OLLAMA_URL") or os.getenv("LLAMA_URL")
        if not ollama_url and llama_enabled not in {"1", "true", "yes", "on"}:
            return {"status": "missing_config", "config": "OLLAMA_URL"}

        from .llama_integration import _check_and_set_flag

        # This performs the actual health check
        await _check_and_set_flag()

        return {"status": "healthy", "url": ollama_url}

    except Exception as e:
        logger.error("Ollama startup health check failed: %s", e)
        return {"status": "error", "error": str(e)}


def should_perform_startup_checks() -> bool:
    """Determine if startup health checks should be performed."""
    return os.getenv("STARTUP_VENDOR_PINGS", "0").strip().lower() in {"1", "true", "yes", "on"}


def get_startup_check_timeout() -> int:
    """Get the timeout for startup health checks."""
    try:
        return int(os.getenv("STARTUP_CHECK_TIMEOUT", "10"))
    except ValueError:
        return 10
