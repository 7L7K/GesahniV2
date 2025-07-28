# app/router.py
import logging
from typing import Any

from .llama_integration import ask_llama, OLLAMA_MODEL
from .gpt_client import ask_gpt, OPENAI_MODEL
from .home_assistant import handle_command
from .intent_detector import detect_intent
from .analytics import record
from .history import append_history  # new import

logger = logging.getLogger(__name__)

async def route_prompt(prompt: str) -> Any:
    # First, handle home-assistant commands
    ha_resp = await handle_command(prompt)

    # Always log every prompt and its response (HA or LLM)
    await append_history(
        prompt=prompt,
        engine="ha" if ha_resp is not None else "llm",
        response=str(ha_resp) if ha_resp is not None else ""
    )

    # If HA handled it, return immediately
    if ha_resp is not None:
        return ha_resp

    # Otherwise route to LLM
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
            logger.error("llama_error", extra={"error": result["error"]})
            # fallback to GPT
            use_llama = False
        else:
            # log LLaMA response
            await append_history(
                prompt=prompt,
                engine="llama",
                response=str(result)
            )
            return result

    # Fallback to GPT
    response = await ask_gpt(prompt, model=OPENAI_MODEL)
    # log GPT response
    await append_history(
        prompt=prompt,
        engine="gpt",
        response=str(response)
    )
    return response
