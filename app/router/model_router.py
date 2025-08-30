"""Model router for selecting and routing to appropriate LLM backends."""

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from ..model_config import GPT_BASELINE_MODEL, GPT_HEAVY_MODEL, GPT_MID_MODEL
from ..model_picker import pick_model
from .debug_flags import is_debug_routing_enabled, is_dry_run_mode
from .rules_loader import get_router_rules

logger = logging.getLogger(__name__)


@dataclass
class RoutingDecision:
    """Data class to encapsulate routing decision information."""
    vendor: str
    model: str
    reason: str
    keyword_hit: Optional[str] = None
    stream: bool = False
    allow_fallback: bool = True
    request_id: Optional[str] = None


class ModelRouter:
    """Handles model selection and routing decisions."""

    def __init__(self):
        # Single source of truth for model allow-lists
        self.allowed_gpt_models = self._get_allowed_models("gpt")
        self.allowed_llama_models = self._get_allowed_models("llama")

    def _get_allowed_models(self, vendor: str) -> set[str]:
        """Get allowed models from environment variables as sets."""
        if vendor == "gpt":
            return set(
                filter(
                    None,
                    os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(","),
                )
            )
        elif vendor == "llama":
            return set(
                filter(
                    None,
                    os.getenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3").split(",")
                )
            )
        return set()

    def _validate_model_allowlist(self, model: str, vendor: str) -> None:
        """Validate model against allow-list before any vendor imports."""
        from fastapi import HTTPException

        if vendor == "openai":
            if model not in self.allowed_gpt_models:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "model_not_allowed",
                        "model": model,
                        "vendor": vendor,
                        "allowed": list(self.allowed_gpt_models),
                    },
                )
        elif vendor == "ollama":
            if model not in self.allowed_llama_models:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "model_not_allowed",
                        "model": model,
                        "vendor": vendor,
                        "allowed": list(self.allowed_llama_models),
                    },
                )
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "unknown_model",
                    "model": model,
                    "hint": f"allowed: {', '.join(self.allowed_gpt_models | self.allowed_llama_models)}",
                },
            )

    def _check_vendor_health(self, vendor: str) -> bool:
        """Check if vendor is healthy without importing vendor modules."""
        if vendor == "openai":
            return self._is_openai_healthy()
        elif vendor == "ollama":
            return self._is_ollama_healthy()
        return False

    def _is_openai_healthy(self) -> bool:
        """Check if OpenAI is healthy."""
        try:
            from ..gpt_client import OPENAI_HEALTHY, openai_circuit_open
            return OPENAI_HEALTHY and not openai_circuit_open
        except Exception:
            return False

    def _is_ollama_healthy(self) -> bool:
        """Check if Ollama is healthy."""
        try:
            from ..llama_integration import LLAMA_HEALTHY, llama_circuit_open
            return LLAMA_HEALTHY and not llama_circuit_open
        except Exception:
            return False

    def _get_fallback_vendor(self, vendor: str) -> str:
        """Get the opposite vendor for fallback."""
        return "ollama" if vendor == "openai" else "openai"

    def _get_fallback_model(self, vendor: str) -> str:
        """Get the default model for the fallback vendor."""
        if vendor == "openai":
            return "gpt-4o"  # Default GPT model
        else:
            return "llama3:latest"  # Default LLaMA model (with tag for consistency)

    def _dry_run_response(self, vendor: str, model: str) -> str:
        """Generate dry-run response message."""
        label = model.split(":")[0] if vendor == "ollama" else model
        msg = f"[dry-run] would call {vendor} {label}"
        logger.info(msg)
        return msg

    def _determine_vendor_and_model_from_override(self, model_override: str) -> tuple[str, str, str]:
        """Determine vendor and model from override string."""
        mv = model_override.strip()
        if mv.startswith("gpt"):
            return "openai", mv, "explicit_override"
        elif mv.startswith("llama"):
            return "ollama", mv, "explicit_override"
        else:
            # Should not happen due to validation in main router
            raise ValueError(f"Invalid model override pattern: {mv}")

    def _determine_vendor_and_model_from_picker(self, prompt: str, intent: str, tokens: int) -> tuple[str, str, str, Optional[str]]:
        """Determine vendor and model using the model picker."""
        engine, model_name, picker_reason, keyword_hit = pick_model(prompt, intent, tokens)
        vendor = "openai" if engine == "gpt" else "ollama"
        return vendor, model_name, picker_reason, keyword_hit

    def _handle_vendor_health_check(self, vendor: str, model: str, reason: str) -> tuple[str, str, str]:
        """Handle vendor health checks and apply fallback logic."""
        if not self._check_vendor_health(vendor):
            if not self._check_vendor_health(self._get_fallback_vendor(vendor)):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "all_vendors_unavailable",
                        "primary": vendor,
                        "fallback": self._get_fallback_vendor(vendor),
                    },
                )

            # Use fallback vendor
            original_vendor = vendor
            fallback_vendor = self._get_fallback_vendor(vendor)
            fallback_model = self._get_fallback_model(fallback_vendor)

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

            return fallback_vendor, fallback_model, f"fallback_{fallback_vendor}"

        return vendor, model, reason

    def route_model(
        self,
        *,
        prompt: str,
        user_id: str,
        intent: str,
        tokens: int,
        model_override: Optional[str] = None,
        allow_fallback: bool = True,
        stream: bool = False,
        request_id: Optional[str] = None,
    ) -> RoutingDecision:
        """Route to appropriate model based on prompt, intent, and overrides."""

        # Handle model override path
        if model_override:
            vendor, model, reason = self._determine_vendor_and_model_from_override(model_override)

            # If Ollama is unhealthy, never dead-end: auto-fallback to OpenAI
            if vendor == "ollama" and not self._check_vendor_health("ollama"):
                fallback_vendor = "openai"
                fallback_model = self._get_fallback_model(fallback_vendor)
                vendor, model, reason = fallback_vendor, fallback_model, "fallback_openai_health"

                logger.info(
                    "router.fallback vendor=ollama->openai reason=health_check_failed",
                    extra={
                        "meta": {
                            "from_vendor": "ollama",
                            "to_vendor": "openai",
                            "reason": "health_check_failed",
                        }
                    },
                )

            # Validate against allow-list
            self._validate_model_allowlist(model, vendor)

            # Check vendor health and handle fallback
            vendor, model, reason = self._handle_vendor_health_check(vendor, model, reason)

        else:
            # Default picker path
            vendor, model, reason, keyword_hit = self._determine_vendor_and_model_from_picker(prompt, intent, tokens)

            # If Ollama is unhealthy, auto-fallback to OpenAI to avoid dead-ends
            if vendor == "ollama" and not self._check_vendor_health("ollama"):
                fallback_vendor = "openai"
                fallback_model = self._get_fallback_model(fallback_vendor)
                vendor, model, reason = fallback_vendor, fallback_model, "fallback_openai_health"

                logger.info(
                    "router.fallback vendor=ollama->openai reason=health_check_failed",
                    extra={
                        "meta": {
                            "from_vendor": "ollama",
                            "to_vendor": "openai",
                            "reason": "health_check_failed",
                        }
                    },
                )

            # Validate against allow-list
            self._validate_model_allowlist(model, vendor)

            # Check vendor health and handle fallback
            vendor, model, reason = self._handle_vendor_health_check(vendor, model, reason)

            keyword_hit = keyword_hit

        # Create routing decision
        decision = RoutingDecision(
            vendor=vendor,
            model=model,
            reason=reason,
            keyword_hit=getattr(locals(), 'keyword_hit', None),
            stream=stream,
            allow_fallback=allow_fallback,
            request_id=request_id,
        )

        # Handle dry-run mode for debug routing
        if is_debug_routing_enabled() and is_dry_run_mode():
            # Return dry-run response instead of actual call
            dry_response = self._dry_run_response(vendor, model)
            # In dry-run mode, we still return a proper RoutingDecision
            # but the caller should handle the dry-run response
            logger.debug("Dry-run mode enabled, would return dry-run response")
            return decision

        return decision


# Global instance for easy access
model_router = ModelRouter()
