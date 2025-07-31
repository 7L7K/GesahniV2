# app/router.py

from __future__ import annotations

import importlib
import json
import logging
import pathlib
import re
from typing import Any

from .analytics import record
from .gpt_client import ask_gpt, OPENAI_MODEL
from .history import append_history
from .home_assistant import handle_command
from .intent_detector import detect_intent
from .llama_integration import LLAMA_HEALTHY, OLLAMA_MODEL, ask_llama
from .telemetry import log_record_var

logger = logging.getLogger(__name__)

# 1. Load keyword catalog ---------------------------------------------------
CAT_PATH = pathlib.Path(__file__).parent / "skills" / "keyword_catalog.json"
try:
    with CAT_PATH.open(encoding="utf-8") as fh:
        _RAW_CATALOG: list[dict[str, Any]] = json.load(fh)
except FileNotFoundError:
    logger.error("keyword_catalog.json not found at %s", CAT_PATH)
    _RAW_CATALOG = []

CATALOG: list[tuple[list[str], type]] = []
for entry in _RAW_CATALOG:
    skill_name = entry.get("skill")
    if not skill_name:
        continue
    module_name = re.sub(r"(?<!^)(?=[A-Z])", "_", skill_name).lower()
    try:
        mod = importlib.import_module(f".skills.{module_name}", package=__package__)
        SkillCls = getattr(mod, skill_name)
        CATALOG.append((entry.get("keywords", []), SkillCls))
    except Exception:
        logger.exception("Failed loading skill %s", skill_name)

# 2. Main routing function --------------------------------------------------
async def route_prompt(prompt: str, model_override: str | None = None) -> Any:
    rec = log_record_var.get()
    if rec:
        rec.prompt = prompt
    logger.debug("route_prompt received: %s", prompt)

    # A) Home‑Assistant
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        if rec:
            rec.engine_used = "ha"
            rec.response = str(ha_resp)
        await append_history(prompt, "ha", str(ha_resp))
        logger.debug("HA handled prompt → %s", ha_resp)
        return ha_resp

    prompt_lower = prompt.lower()
    # B) Catalog skills
    for keywords, SkillCls in CATALOG:
        logger.debug("Trying %s with keywords %s", SkillCls.__name__, keywords)
        if any(kw in prompt_lower for kw in keywords):
            skill = SkillCls()
            try:
                result = await skill.handle(prompt)
            except ValueError as ve:
                logger.debug("%s pattern miss: %s", SkillCls.__name__, ve)
                continue
            except Exception as exc:
                logger.exception("%s error: %s", SkillCls.__name__, exc)
                continue

            skill_name = getattr(skill, "name", skill.__class__.__name__)
            if rec:
                rec.engine_used = skill_name
                rec.response = str(result)
            await append_history(prompt, skill_name, str(result))
            await record(skill_name)
            logger.debug("Catalog match → %s", skill_name)
            return result

    # C) Model selection
    if model_override:
        use_llama_pref = model_override.lower().startswith("llama")
        llama_model = model_override
        gpt_model = OPENAI_MODEL
        confidence = "override"
    else:
        intent, confidence = detect_intent(prompt)
        use_llama_pref = len(prompt) < 250 and confidence in ("medium", "high")
        llama_model = OLLAMA_MODEL
        gpt_model = OPENAI_MODEL

    use_llama = use_llama_pref and LLAMA_HEALTHY
    fallback_used = use_llama_pref
    chosen_model = llama_model if use_llama else gpt_model
    engine_used = "llama" if use_llama else "gpt"

    logger.info(
        "routing_decision",
        extra={
            "meta": {
                "prompt_length": len(prompt),
                "intent_confidence": confidence,
                "engine_used": chosen_model,
            }
        },
    )

    # D) LLaMA
    if use_llama:
        result = await ask_llama(prompt, llama_model)
        if isinstance(result, dict) and "error" in result:
            logger.error("llama_error", extra={"error": result["error"]})
        else:
            if rec:
                rec.engine_used = engine_used
                rec.response = str(result)
                rec.model_name = llama_model
            await append_history(prompt, engine_used, str(result))
            await record("llama")
            logger.debug("LLaMA responded OK")
            return result

    # E) GPT fallback, bias 3.5 for light skills
    light_skill_hint = any(
        kw in prompt_lower
        for kw in ["translate", "search ", "remind", "reminder"]
    )
    final_model = "gpt-3.5-turbo" if light_skill_hint else chosen_model

    text, pt, ct, unit_price = await ask_gpt(prompt, final_model)
    if rec:
        rec.engine_used = "gpt"
        rec.response = text
        rec.model_name = final_model
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * unit_price

    await append_history(prompt, "gpt", text)
    await record("gpt", fallback=fallback_used)
    logger.debug("GPT responded OK with %s", final_model)
    return text
