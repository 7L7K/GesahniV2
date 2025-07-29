import logging
from typing import Any

from .llama_integration import ask_llama, OLLAMA_MODEL, LLAMA_HEALTHY
from .gpt_client import ask_gpt, OPENAI_MODEL
from .home_assistant import handle_command
from .intent_detector import detect_intent
from .analytics import record                # ⬅︎ kept as‑is
from .history import append_history          # ⬅︎ signature unchanged
from .telemetry import log_record_var

logger = logging.getLogger(__name__)


async def route_prompt(prompt: str, model_override: str | None = None) -> Any:
    print("➡️ route_prompt fired with prompt:", prompt)
    rec = log_record_var.get()
    if rec is not None:
        rec.prompt = prompt

    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        if rec is not None:
            rec.engine_used = "ha"
            rec.response = str(ha_resp)
        print("🛠 About to log HA response...")
        await append_history(prompt, "ha", str(ha_resp))
        print("✅ HA response logged.")
        return ha_resp

    if model_override:
        would_use_llama = model_override.lower().startswith("llama")
        model = model_override
        gpt_model = model_override if not would_use_llama else OPENAI_MODEL
        confidence = "override"
    else:
        intent, confidence = detect_intent(prompt)
        would_use_llama = len(prompt) < 250 and confidence in ("medium", "high")
        model = OLLAMA_MODEL if would_use_llama else OPENAI_MODEL
        gpt_model = OPENAI_MODEL
    use_llama = would_use_llama and LLAMA_HEALTHY
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
        result = await ask_llama(prompt, model)
        if isinstance(result, dict) and "error" in result:
            logger.error("llama_error", extra={"error": result["error"]})
        else:
            if rec is not None:
                rec.engine_used = engine_used
                rec.response = str(result)
                rec.model_name = model
            print("🧠 About to log LLaMA result...")
            await append_history(prompt, engine_used, str(result))
            await record("llama")
            print("✅ LLaMA response logged.")
            return result

    print("🤖 About to log GPT result...")
    text, pt, ct, price = await ask_gpt(prompt, gpt_model if not use_llama else None)
    if rec is not None:
        rec.engine_used = "gpt"
        rec.response = str(text)
        rec.model_name = gpt_model if not use_llama else OPENAI_MODEL
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * price
    await append_history(prompt, "gpt", str(text))
    await record("gpt", fallback=would_use_llama)
    print("✅ GPT response logged.")
    return text
