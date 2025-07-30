"""Prompt routing module

This version resolves merge‑conflict markers, drops the unused
`SKILL_PATTERNS` prototype, and keeps the keyword‑catalog approach.
It also clarifies model‑selection logic and ensures every pathway
updates telemetry + history consistently.
"""

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

# ---------------------------------------------------------------------------
# 1.  Load keyword catalog ---------------------------------------------------
# ---------------------------------------------------------------------------
CAT_PATH = pathlib.Path(__file__).parent / "skills" / "keyword_catalog.json"
try:
    with CAT_PATH.open(encoding="utf-8") as fh:
        _RAW_CATALOG: list[dict[str, Any]] = json.load(fh)
except FileNotFoundError:
    logger.error("keyword_catalog.json not found at %s", CAT_PATH)
    _RAW_CATALOG = []

# Build (keywords, SkillCls) lookup table
CATALOG: list[tuple[list[str], type]] = []
for entry in _RAW_CATALOG:
    skill_name: str | None = entry.get("skill")
    if not skill_name:
        continue

    # CamelCase → snake_case (e.g. MathSkill → math_skill)
    module_name = re.sub(r"(?<!^)(?=[A-Z])", "_", skill_name).lower()
    try:
        mod = importlib.import_module(f".skills.{module_name}", package=__package__)
        SkillCls = getattr(mod, skill_name)
        CATALOG.append((entry.get("keywords", []), SkillCls))
    except Exception as exc:
        logger.exception("Failed loading skill %s: %s", skill_name, exc)

# ---------------------------------------------------------------------------
# 2.  Main routing function --------------------------------------------------
# ---------------------------------------------------------------------------
async def route_prompt(prompt: str, model_override: str | None = None) -> Any:
    """Route *prompt* through:
    A) Home‑Assistant commands,
    B) Keyword‑triggered custom skills, or
    C) LLaMA / GPT model fallback.
    """

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

    # ---- B. Catalog‑based skill routing -----------------------------------
    prompt_lower = prompt.lower()
    for keywords, SkillCls in CATALOG:
        if any(kw in prompt_lower for kw in keywords):
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

    # ---- C. Model selection (LLaMA vs GPT) --------------------------------
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
    model_chosen = llama_model if use_llama else gpt_model
    engine_used = "llama" if use_llama else "gpt"

    logger.info(
        "routing_decision",
        extra={
            "meta": {
                "prompt_length": len(prompt),
                "intent_confidence": confidence,
                "engine_used": model_chosen,
            }
        },
    )

    # ---- D. LLaMA pathway --------------------------------------------------
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

    # ---- E. GPT (fallback or primary) -------------------------------------
    text, pt, ct, price = await ask_gpt(prompt, gpt_model)
    if rec:
        rec.engine_used = "gpt"
        rec.response = str(text)
        rec.model_name = gpt_model
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * price

    await append_history(prompt, "gpt", str(text))
    await record("gpt", fallback=use_llama)
    logger.debug("GPT responded OK")
    return text
