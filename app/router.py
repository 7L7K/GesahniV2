from __future__ import annotations

import logging
import re
from typing import Any

from .analytics import record
from .gpt_client import ask_gpt, SYSTEM_PROMPT
from .history import append_history
from .home_assistant import handle_command
from .llama_integration import LLAMA_HEALTHY, OLLAMA_MODEL, ask_llama
from .telemetry import log_record_var
from .memory import memgpt
from .memory.vector_store import add_user_memory, cache_answer, lookup_cached_answer
from .prompt_builder import PromptBuilder
from .skills.base import check_builtin_skills

logger = logging.getLogger(__name__)


# Main routing function ------------------------------------------------------
async def route_prompt(prompt: str, model_override: str | None = None) -> Any:
    rec = log_record_var.get()
    if rec:
        rec.prompt = prompt
    session_id = rec.session_id if rec and rec.session_id else "default"
    user_id = rec.user_id if rec and rec.user_id else "anon"
    logger.debug("route_prompt received: %s", prompt)

    # A) Built‑in skills
    skill_resp = await check_builtin_skills(prompt)
    if skill_resp is not None:
        if rec:
            rec.engine_used = "skill"
            rec.response = str(skill_resp)
        await append_history(prompt, "skill", str(skill_resp))
        await record("skill", source="skill")
        logger.debug("Built-in skill handled prompt")
        return skill_resp

    # B) Home Assistant
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        if rec:
            rec.engine_used = "ha"
            rec.response = str(ha_resp)
        await append_history(prompt, "ha", str(ha_resp))
        logger.debug("HA handled prompt → %s", ha_resp)
        return ha_resp

    # C) Cache lookup
    cached = lookup_cached_answer(prompt)
    if cached is not None:
        if rec:
            rec.engine_used = "cache"
            rec.response = cached
        await append_history(prompt, "cache", cached)
        await record("cache", source="cache")
        logger.debug("Cache hit")
        return cached

    # D) Build prompt with context
    custom_instr = getattr(rec, "custom_instructions", "") if rec else ""
    debug_flag = getattr(rec, "debug", False) if rec else False
    debug_info = getattr(rec, "debug_info", "") if rec else ""
    built_prompt, ptokens = PromptBuilder.build(
        prompt,
        session_id=session_id,
        user_id=user_id,
        custom_instructions=custom_instr,
        debug=debug_flag,
        debug_info=debug_info,
    )
    if rec:
        rec.prompt_tokens = ptokens

    # E) LLaMA first
    if LLAMA_HEALTHY:
        llama_model = model_override if model_override and model_override.lower().startswith("llama") else OLLAMA_MODEL
        result = await ask_llama(built_prompt, llama_model)
        if not (isinstance(result, dict) and "error" in result):
            result_text = str(result).strip()
            if result_text and not _low_conf(result_text):
                if rec:
                    rec.engine_used = "llama"
                    rec.response = result_text
                    rec.model_name = llama_model
                await append_history(prompt, "llama", result_text)
                await record("llama")
                memgpt.store_interaction(prompt, result_text, session_id=session_id)
                add_user_memory(user_id, f"Q: {prompt}\nA: {result_text}")
                cache_answer(prompt, result_text)
                logger.debug("LLaMA responded OK")
                return result_text

    # F) GPT-4o fallback
    text, pt, ct, unit_price = await ask_gpt(built_prompt, "gpt-4o", SYSTEM_PROMPT)
    if rec:
        rec.engine_used = "gpt"
        rec.response = text
        rec.model_name = "gpt-4o"
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * unit_price

    await append_history(prompt, "gpt", text)
    await record("gpt", fallback=True)
    memgpt.store_interaction(prompt, text, session_id=session_id)
    add_user_memory(user_id, f"Q: {prompt}\nA: {text}")
    cache_answer(prompt, text)
    logger.debug("GPT responded OK with gpt-4o")
    return text


def _low_conf(resp: str) -> bool:
    if len(resp.split()) < 3:
        return True
    if re.search(r"\b(i don't know|i am not sure|not sure|cannot help)\b", resp, re.I):
        return True
    return False
