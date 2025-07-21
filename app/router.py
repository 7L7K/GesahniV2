import logging
import re
from typing import Callable

from .llama_client import llama_completion
from .gpt_client import gpt_completion

logger = logging.getLogger(__name__)


def _should_use_gpt(prompt: str) -> bool:
    """Rudimentary intent detection."""
    complex_keywords = ["code", "research", "analysis", "step", "logic"]
    return any(word in prompt.lower() for word in complex_keywords)


def route_prompt(prompt: str, fallback: bool = True) -> str:
    """Route the prompt to the correct model with optional fallback."""
    service: Callable[[str], str]
    use_gpt = _should_use_gpt(prompt)

    # Choose primary service
    if use_gpt:
        primary = gpt_completion
        secondary = llama_completion
    else:
        primary = llama_completion
        secondary = gpt_completion

    try:
        return primary(prompt)
    except Exception as first_error:
        logger.error("Primary service failed: %s", first_error)
        if fallback:
            try:
                return secondary(prompt)
            except Exception as second_error:
                logger.error("Secondary service failed: %s", second_error)
                raise RuntimeError(
                    f"Both services failed: {first_error}; {second_error}")
        raise
