import logging
from typing import Any

from .llama_client import ask_llama, OLLAMA_MODEL
from .gpt_client import ask_gpt, OPENAI_MODEL
from .home_assistant import handle_command
from .intent_detector import detect_intent
from .analytics import record
from .history import append_history

logger = logging.getLogger(__name__)


async def route_prompt(prompt: str) -> Any:
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        return ha_resp

    intent, confidence = detect_intent(prompt)
    use_llama = len(prompt) < 250 and confidence in ("medium", "high")
    engine = "llama" if use_llama else "gpt"
    model = OLLAMA_MODEL if use_llama else OPENAI_MODEL
    logger.info(
        "routing_decision",
        extra={
            "meta": {
                "prompt_length": len(prompt),
                "intent_confidence": confidence,
                "engine_used": model,
            }
        },
    )

    if use_llama:
        result = await ask_llama(prompt)
        if isinstance(result, dict) and "error" in result:
            logger.error("llama_error", extra={"meta": result})
            await record("gpt", fallback=True)
            answer = await ask_gpt(prompt)
            await append_history(prompt, OPENAI_MODEL, answer)
            return answer
        await record("llama")
        await append_history(prompt, OLLAMA_MODEL, result)
        return result

    try:
        answer = await ask_gpt(prompt)
        await record("gpt")
        await append_history(prompt, OPENAI_MODEL, answer)
        return answer
    except Exception:
        logger.exception("gpt_failure", extra={"meta": {"engine_used": OPENAI_MODEL}})
        fallback = await ask_llama(prompt)
        await record("llama", fallback=True)
        await append_history(prompt, OLLAMA_MODEL, fallback)
        return fallback
