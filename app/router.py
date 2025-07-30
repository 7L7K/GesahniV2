import json
import logging
import pathlib
import importlib
import re  # added for CamelCase to snake_case conversion
from typing import Any

from .llama_integration import ask_llama, OLLAMA_MODEL, LLAMA_HEALTHY
from .gpt_client import ask_gpt, OPENAI_MODEL
from .home_assistant import handle_command
from .intent_detector import detect_intent
from .analytics import record
from .history import append_history
from .telemetry import log_record_var

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1.  Load keyword catalog ----------------------------------------------------
# ---------------------------------------------------------------------------
CAT_PATH = pathlib.Path(__file__).parent / "skills" / "keyword_catalog.json"
try:
    with CAT_PATH.open(encoding="utf-8") as fh:
        _RAW_CATALOG = json.load(fh)
except FileNotFoundError:
    logger.error("keyword_catalog.json not found at %s", CAT_PATH)
    _RAW_CATALOG = []

CATALOG: list[tuple[list[str], type]] = []
for entry in _RAW_CATALOG:
    skill_name = entry.get("skill")
    try:
        # Convert CamelCase skill name to snake_case module filename
        module_name = re.sub(r'(?<!^)(?=[A-Z])', '_', skill_name).lower()
        mod = importlib.import_module(f".skills.{module_name}", package="app")
        SkillCls = getattr(mod, skill_name)
        CATALOG.append((entry.get("keywords", []), SkillCls))
    except Exception as exc:  # startup failure is fatal
        logger.exception("Failed loading skill %s: %s", skill_name, exc)

# ---------------------------------------------------------------------------
# 2.  Main routing function ---------------------------------------------------
# ---------------------------------------------------------------------------
async def route_prompt(prompt: str, model_override: str | None = None) -> Any:
    rec = log_record_var.get()
    if rec:
        rec.prompt = prompt
    logger.debug("route_prompt received: %s", prompt)

    # ---- A. Home‑Assistant short‑circuit ----------------------------------
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        if rec:
            rec.engine_used = "ha"
            rec.response = str(ha_resp)
        await append_history(prompt, "ha", str(ha_resp))
        logger.debug("HA handled prompt → %s", ha_resp)
        return ha_resp

    # ---- B. Catalog‑based skill routing ------------------------------------
    lower = prompt.lower()
    for keywords, SkillCls in CATALOG:
        if any(kw in lower for kw in keywords):
            skill = SkillCls()
            result = await skill.handle(prompt)
            skill_name = getattr(skill, "name", skill.__class__.__name__)
            if rec:
                rec.engine_used = skill_name
                rec.response = str(result)
            await append_history(prompt, skill_name, str(result))
            await record(skill_name)
            logger.debug("%s handled prompt", skill_name)
            return result

    # ---- C. Model selection (LLaMA vs GPT) ----------------------------------
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

    # ---- D. LLaMA path -----------------------------------------------------
    if use_llama:
        result = await ask_llama(prompt, model)
        if isinstance(result, dict) and "error" in result:
            logger.error("llama_error", extra={"error": result["error"]})
        else:
            if rec:
                rec.engine_used = engine_used
                rec.response = str(result)
                rec.model_name = model
            await append_history(prompt, engine_used, str(result))
            await record("llama")
            logger.debug("LLaMA responded OK")
            return result

    # ---- E. GPT fallback ---------------------------------------------------
    text, pt, ct, price = await ask_gpt(prompt, gpt_model if not use_llama else None)
    if rec:
        rec.engine_used = "gpt"
        rec.response = str(text)
        rec.model_name = gpt_model if not use_llama else OPENAI_MODEL
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * price
    await append_history(prompt, "gpt", str(text))
    await record("gpt", fallback=would_use_llama)
    logger.debug("GPT responded OK")
    return text
