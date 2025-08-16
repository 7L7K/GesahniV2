import os
import re
import logging
from typing import Tuple

from . import llama_integration
from .model_config import GPT_HEAVY_MODEL

logger = logging.getLogger(__name__)

HEAVY_WORD_COUNT = int(os.getenv("MODEL_ROUTER_HEAVY_WORDS", "30"))
HEAVY_TOKENS = int(os.getenv("MODEL_ROUTER_HEAVY_TOKENS", "1000"))

# Updated keywords from environment variable
DEFAULT_KEYWORDS = "code,unit test,analyze,sql,benchmark,vector"
KEYWORDS = set(os.getenv("MODEL_ROUTER_KEYWORDS", DEFAULT_KEYWORDS).split(","))
HEAVY_INTENTS = {"analysis", "research"}


def pick_model(prompt: str, intent: str, tokens: int) -> Tuple[str, str, str, str | None]:
    """Route prompt to the best engine/model for the task."""
    prompt_lc = prompt.lower()
    words = re.findall(r"\w+", prompt_lc)
    
    print(f"🎯 PICK_MODEL: prompt_len={len(prompt)}, words={len(words)}, tokens={tokens}, intent={intent}")
    
    # Check for heavy tasks
    if len(words) > HEAVY_WORD_COUNT:
        print(f"🎯 PICK_MODEL: HEAVY TASK → GPT (words={len(words)}, tokens={tokens}, intent={intent})")
        logger.info(
            f"Routing to GPT: words={len(words)}, tokens={tokens}, "
            f"intent={intent}, prompt='{prompt[:60]}...'"
        )
        return "gpt", GPT_HEAVY_MODEL, "heavy_length", None
    
    if tokens > HEAVY_TOKENS:
        print(f"🎯 PICK_MODEL: HEAVY TASK → GPT (words={len(words)}, tokens={tokens}, intent={intent})")
        logger.info(
            f"Routing to GPT: words={len(words)}, tokens={tokens}, "
            f"intent={intent}, prompt='{prompt[:60]}...'"
        )
        return "gpt", GPT_HEAVY_MODEL, "heavy_tokens", None
    
    # Check for keywords
    for keyword in KEYWORDS:
        if keyword.lower() in prompt_lc:
            print(f"🎯 PICK_MODEL: HEAVY TASK → GPT (keyword='{keyword}', tokens={tokens}, intent={intent})")
            logger.info(
                f"Routing to GPT: keyword='{keyword}', tokens={tokens}, "
                f"intent={intent}, prompt='{prompt[:60]}...'"
            )
            return "gpt", GPT_HEAVY_MODEL, "keyword", keyword
    
    if intent in HEAVY_INTENTS:
        print(f"🎯 PICK_MODEL: HEAVY TASK → GPT (words={len(words)}, tokens={tokens}, intent={intent})")
        logger.info(
            f"Routing to GPT: words={len(words)}, tokens={tokens}, "
            f"intent={intent}, prompt='{prompt[:60]}...'"
        )
        return "gpt", GPT_HEAVY_MODEL, "heavy_intent", None

    llama_model = llama_integration.OLLAMA_MODEL or os.getenv(
        "OLLAMA_MODEL", "llama3:latest"
    )
    if not llama_model:
        logger.warning("No LLAMA model configured—using fallback 'llama'")
    if not llama_integration.LLAMA_HEALTHY or llama_integration.llama_circuit_open:
        print(f"🎯 PICK_MODEL: LLAMA UNAVAILABLE → GPT (healthy={llama_integration.LLAMA_HEALTHY}, circuit={llama_integration.llama_circuit_open})")
        logger.info("LLaMA unavailable, routing to GPT")
        reason = "circuit_breaker" if llama_integration.llama_circuit_open else "llama_unhealthy"
        return "gpt", GPT_HEAVY_MODEL, reason, None
    
    print(f"🎯 PICK_MODEL: LIGHT TASK → LLAMA ({llama_model})")
    return "llama", llama_model, "light_default", None
