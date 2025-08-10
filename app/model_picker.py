import os
import re
import logging
from typing import Tuple

from . import llama_integration
from .model_config import GPT_HEAVY_MODEL

logger = logging.getLogger(__name__)

HEAVY_WORD_COUNT = int(os.getenv("MODEL_ROUTER_HEAVY_WORDS", "30"))
HEAVY_TOKENS = int(os.getenv("MODEL_ROUTER_HEAVY_TOKENS", "1000"))

KEYWORDS = {"code", "research", "analyze", "explain", "diagram", "summarize"}
HEAVY_INTENTS = {"analysis", "research"}


def pick_model(prompt: str, intent: str, tokens: int) -> Tuple[str, str]:
    """Route prompt to the best engine/model for the task."""
    prompt_lc = prompt.lower()
    words = re.findall(r"\w+", prompt_lc)
    if (
        len(words) > HEAVY_WORD_COUNT
        or any(re.search(rf"\b{k}\b", prompt_lc) for k in KEYWORDS)
        or tokens > HEAVY_TOKENS
        or intent in HEAVY_INTENTS
    ):
        logger.info(
            f"Routing to GPT: words={len(words)}, tokens={tokens}, "
            f"intent={intent}, prompt='{prompt[:60]}...'"
        )
        return "gpt", GPT_HEAVY_MODEL

    llama_model = llama_integration.OLLAMA_MODEL or os.getenv(
        "OLLAMA_MODEL", "llama3:latest"
    )
    if not llama_model:
        logger.warning("No LLAMA model configured—using fallback 'llama'")
    if not llama_integration.LLAMA_HEALTHY or llama_integration.llama_circuit_open:
        logger.info("LLaMA unavailable, routing to GPT")
        return "gpt", GPT_HEAVY_MODEL
    return "llama", llama_model
