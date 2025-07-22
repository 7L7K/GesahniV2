import logging
from .llama_integration import ask_llama, OLLAMA_MODEL
from .gpt_client import ask_gpt, OPENAI_MODEL
from .home_assistant import handle_command
from .intent_detector import detect_intent
from .analytics import record

logger = logging.getLogger(__name__)

async def route_prompt(prompt: str) -> str:
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        return ha_resp

    intent, confidence = detect_intent(prompt)
    use_llama = len(prompt) < 250 and confidence in {"medium", "high"}
    log_data = {
        "prompt_length": len(prompt),
        "intent_confidence": confidence,
    }

    if use_llama:
        try:
            resp = await ask_llama(prompt)
            if isinstance(resp, dict) and "error" in resp:
                raise RuntimeError("llama error")
            await record("llama")
            log_data["engine_used"] = OLLAMA_MODEL
            logger.info("routing_decision", extra={"meta": log_data})
            return resp
        except Exception:
            logger.exception("LLaMA failed", extra={"meta": log_data})
            resp = await ask_gpt(prompt)
            await record("gpt", True)
            log_data["engine_used"] = OPENAI_MODEL
            logger.info("routing_decision", extra={"meta": log_data})
            return resp
    else:
        try:
            resp = await ask_gpt(prompt)
            await record("gpt")
            log_data["engine_used"] = OPENAI_MODEL
            logger.info("routing_decision", extra={"meta": log_data})
            return resp
        except Exception:
            logger.exception("GPT failed", extra={"meta": log_data})
            resp = await ask_llama(prompt)
            if isinstance(resp, dict) and "error" in resp:
                await record("llama", True)
                log_data["engine_used"] = OLLAMA_MODEL
                logger.info("routing_decision", extra={"meta": log_data})
                return str(resp)
            await record("llama", True)
            log_data["engine_used"] = OLLAMA_MODEL
            logger.info("routing_decision", extra={"meta": log_data})
            return resp
