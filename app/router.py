import logging
from typing import Any

from .llama_integration import ask_llama, OLLAMA_MODEL
from .gpt_client import ask_gpt, OPENAI_MODEL
from .home_assistant import handle_command
from .intent_detector import detect_intent
from .analytics import record                # ⬅︎ kept as‑is
from .history import append_history          # ⬅︎ signature unchanged

logger = logging.getLogger(__name__)


async def route_prompt(prompt: str) -> Any:
    print("➡️ route_prompt fired with prompt:", prompt)

    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        print("🛠 About to log HA response...")
        await append_history(prompt, "ha", str(ha_resp))
        print("✅ HA response logged.")
        return ha_resp

    intent, confidence = detect_intent(prompt)
    use_llama = len(prompt) < 250 and confidence in ("medium", "high")
    model = OLLAMA_MODEL if use_llama else OPENAI_MODEL
    engine_used = "llama" if use_llama else "gpt"

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
        else:
            print("🧠 About to log LLaMA result...")
            await append_history(prompt, engine_used, str(result))
            await record("llama")
            print("✅ LLaMA response logged.")
            return result

    print("🤖 About to log GPT result...")
    response = await ask_gpt(prompt)
    await append_history(prompt, "gpt", str(response))
    await record("gpt", fallback=use_llama)
    print("✅ GPT response logged.")
    return response
