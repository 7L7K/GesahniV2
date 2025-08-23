import logging
import os
import re

from . import llama_integration
from .model_config import GPT_HEAVY_MODEL

logger = logging.getLogger(__name__)

HEAVY_WORD_COUNT = int(os.getenv("MODEL_ROUTER_HEAVY_WORDS", "30"))
HEAVY_TOKENS = int(os.getenv("MODEL_ROUTER_HEAVY_TOKENS", "1000"))

# Updated keywords from environment variable
DEFAULT_KEYWORDS = "code,unit test,analyze,sql,benchmark,vector"
KEYWORDS = set(os.getenv("MODEL_ROUTER_KEYWORDS", DEFAULT_KEYWORDS).split(","))
HEAVY_INTENTS = {"analysis", "research"}


def pick_model(prompt: str, intent: str, tokens: int) -> tuple[str, str, str, str | None]:
    """Route prompt to the best engine/model for the task."""
    prompt_lc = prompt.lower()
    words = re.findall(r"\w+", prompt_lc)
    
    logger.info(
        "🎯 PICK_MODEL: prompt_len=%d, words=%d, tokens=%d, intent=%s",
        len(prompt), len(words), tokens, intent,
        extra={
            "meta": {
                "prompt_length": len(prompt),
                "word_count": len(words),
                "token_count": tokens,
                "intent": intent,
            }
        }
    )
    
    # Check for heavy tasks
    if len(words) > HEAVY_WORD_COUNT:
        logger.info(
            "🎯 PICK_MODEL: HEAVY TASK → GPT (words=%d, tokens=%d, intent=%s)",
            len(words), tokens, intent,
            extra={
                "meta": {
                    "word_count": len(words),
                    "token_count": tokens,
                    "intent": intent,
                    "reason": "heavy_length",
                }
            }
        )
        return "gpt", GPT_HEAVY_MODEL, "heavy_length", None
    
    if tokens > HEAVY_TOKENS:
        logger.info(
            "🎯 PICK_MODEL: HEAVY TASK → GPT (words=%d, tokens=%d, intent=%s)",
            len(words), tokens, intent,
            extra={
                "meta": {
                    "word_count": len(words),
                    "token_count": tokens,
                    "intent": intent,
                    "reason": "heavy_tokens",
                }
            }
        )
        return "gpt", GPT_HEAVY_MODEL, "heavy_tokens", None
    
    # Check for keywords
    for keyword in KEYWORDS:
        if keyword.lower() in prompt_lc:
            logger.info(
                "🎯 PICK_MODEL: HEAVY TASK → GPT (keyword='%s', tokens=%d, intent=%s)",
                keyword, tokens, intent,
                extra={
                    "meta": {
                        "keyword": keyword,
                        "token_count": tokens,
                        "intent": intent,
                        "reason": "keyword",
                    }
                }
            )
            return "gpt", GPT_HEAVY_MODEL, "keyword", keyword
    
    if intent in HEAVY_INTENTS:
        logger.info(
            "🎯 PICK_MODEL: HEAVY TASK → GPT (words=%d, tokens=%d, intent=%s)",
            len(words), tokens, intent,
            extra={
                "meta": {
                    "word_count": len(words),
                    "token_count": tokens,
                    "intent": intent,
                    "reason": "heavy_intent",
                }
            }
        )
        return "gpt", GPT_HEAVY_MODEL, "heavy_intent", None

    llama_model = llama_integration.OLLAMA_MODEL or os.getenv(
        "OLLAMA_MODEL", "llama3:latest"
    )
    if not llama_model:
        logger.warning("No LLAMA model configured—using fallback 'llama'")
    if not llama_integration.LLAMA_HEALTHY or llama_integration.llama_circuit_open:
        logger.info(
            "🎯 PICK_MODEL: LLAMA UNAVAILABLE → GPT (healthy=%s, circuit=%s)",
            llama_integration.LLAMA_HEALTHY, llama_integration.llama_circuit_open,
            extra={
                "meta": {
                    "llama_healthy": llama_integration.LLAMA_HEALTHY,
                    "circuit_open": llama_integration.llama_circuit_open,
                    "reason": "circuit_breaker" if llama_integration.llama_circuit_open else "llama_unhealthy",
                }
            }
        )
        reason = "circuit_breaker" if llama_integration.llama_circuit_open else "llama_unhealthy"
        return "gpt", GPT_HEAVY_MODEL, reason, None
    
    logger.info(
        "🎯 PICK_MODEL: LIGHT TASK → LLAMA (%s)",
        llama_model,
        extra={"meta": {"model": llama_model, "reason": "light_default"}}
    )
    return "llama", llama_model, "light_default", None
