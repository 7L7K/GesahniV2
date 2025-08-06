import os
import re
import logging
from typing import Tuple

from .llama_integration import OLLAMA_MODEL

logger = logging.getLogger(__name__)

GPT_DEFAULT_MODEL = os.getenv("GPT_DEFAULT_MODEL", "gpt-4o")
LLAMA_DEFAULT_MODEL = OLLAMA_MODEL or os.getenv("OLLAMA_MODEL", "llama3:latest")
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
        return "gpt", GPT_DEFAULT_MODEL

    if not LLAMA_DEFAULT_MODEL:
        logger.warning("No LLAMA model configured—using fallback 'llama'")
    return "llama", LLAMA_DEFAULT_MODEL
