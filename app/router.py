from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import HTTPException, Depends

from .analytics import record
from .gpt_client import ask_gpt, SYSTEM_PROMPT
from .history import append_history
from .home_assistant import handle_command
from .memory.vector_store import (
    add_user_memory,
    cache_answer,
    lookup_cached_answer,
)
from .llama_integration import ask_llama, LLAMA_HEALTHY
from .model_picker import pick_model
from .telemetry import log_record_var
from .memory import memgpt
from .prompt_builder import PromptBuilder
from .token_utils import count_tokens
from .skills.base import SKILLS as BUILTIN_CATALOG, check_builtin_skills
from . import skills  # populate built-in registry (SmalltalkSkill, etc.)  # noqa: F401
from .intent_detector import detect_intent
from .deps.user import get_current_user_id

logger = logging.getLogger(__name__)

# Expose this so tests can override/inspect it
ALLOWED_GPT_MODELS = set(
    os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(",")
)
# Expose catalog so tests can monkey-patch it
CATALOG = BUILTIN_CATALOG


async def route_prompt(
    prompt: str,
    model_override: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> Any:
    rec = log_record_var.get()
    tokens = count_tokens(prompt)
    if rec:
        rec.prompt = prompt
        rec.embed_tokens = tokens
        rec.user_id = user_id
    session_id = rec.session_id if rec and rec.session_id else "default"
    logger.debug("route_prompt received: %s", prompt)
    norm_prompt = prompt.lower().strip()
    debug_model_routing = os.getenv("DEBUG_MODEL_ROUTING", "").lower() in {
        "1",
        "true",
        "yes",
    }

    def _dry_return(engine: str, model: str) -> str:
        msg = f"[dry-run] would call {engine} {model}"
        logger.info(msg)
        if rec:
            rec.engine_used = engine
            rec.model_name = model
            rec.response = msg
        return msg

    # Intent detection
    intent, priority = detect_intent(prompt)
    # Smalltalk shortcut
    if intent == "smalltalk":
        from .skills.smalltalk_skill import SmalltalkSkill

        skill_resp = await SmalltalkSkill().handle(prompt)
        if rec:
            rec.engine_used = "skill"
        await append_history(prompt, "skill", str(skill_resp))
        await record("done", source="skill")
        return skill_resp

    skip_skills = intent == "chat" and priority == "high"

    # Model override block
    if model_override is not None:
        if model_override in ALLOWED_GPT_MODELS:
            built, ptokens = PromptBuilder.build(
                prompt, session_id=session_id, user_id=user_id
            )
            if debug_model_routing:
                return _dry_return("gpt", model_override)
            text, pt, ct, unit_price = await ask_gpt(
                built, model_override, SYSTEM_PROMPT
            )
            if rec:
                rec.engine_used = "gpt"
                rec.response = text
                rec.model_name = model_override
                rec.prompt_tokens = pt
                rec.completion_tokens = ct
                rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * unit_price
            await append_history(prompt, "gpt", text)
            await record("gpt", fallback=True)
            memgpt.store_interaction(
                prompt, text, session_id=session_id, user_id=user_id
            )
            add_user_memory(user_id, f"Q: {prompt}\nA: {text}")
            cache_answer(norm_prompt, text)
            return text
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Model override {model_override} not allowed",
            )

    # Built-in skills
    if not skip_skills:
        for entry in CATALOG:
            if isinstance(entry, tuple) and len(entry) == 2:
                keywords, SkillClass = entry
                if any(kw in prompt for kw in keywords):
                    skill_resp = await SkillClass().handle(prompt)
                    if rec:
                        rec.engine_used = "skill"
                    await append_history(prompt, "skill", str(skill_resp))
                    await record("done", source="skill")
                    return skill_resp
        skill_resp = await check_builtin_skills(prompt)
        if skill_resp is not None:
            if rec:
                rec.engine_used = "skill"
            await append_history(prompt, "skill", str(skill_resp))
            await record("done", source="skill")
            return skill_resp

    # Home Assistant commands
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        if rec:
            rec.engine_used = "ha"
            rec.response = ha_resp.message
        await append_history(prompt, "ha", ha_resp.message)
        logger.debug("HA handled prompt → %s", ha_resp.message)
        return ha_resp

    # Cache lookup
    if rec:
        rec.cache_hit = bool(lookup_cached_answer(norm_prompt))
    cached = lookup_cached_answer(norm_prompt)
    if cached is not None:
        if rec:
            rec.engine_used = "cache"
            rec.response = cached
        await append_history(prompt, "cache", cached)
        await record("cache", source="cache")
        logger.debug("Cache hit for prompt: %s", norm_prompt)
        return cached

    # Delegate model choice
    engine, model_name = pick_model(prompt, intent, tokens)

    # Build prompt with context
    built_prompt, ptokens = PromptBuilder.build(
        prompt,
        session_id=session_id,
        user_id=user_id,
        custom_instructions=getattr(rec, "custom_instructions", ""),
        debug=os.getenv("DEBUG", "").lower() in {"1", "true", "yes"},
        debug_info=getattr(rec, "debug_info", ""),
    )
    if rec:
        rec.prompt_tokens = ptokens

    # GPT path
    if engine == "gpt":
        if debug_model_routing:
            return _dry_return("gpt", model_name)
        text, pt, ct, unit_price = await ask_gpt(
            built_prompt, model_name, SYSTEM_PROMPT
        )
        if rec:
            rec.engine_used = "gpt"
            rec.response = text
            rec.model_name = model_name
            rec.prompt_tokens = pt
            rec.completion_tokens = ct
            rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * unit_price
        await append_history(prompt, "gpt", text)
        await record("gpt", source="model_picker")
        memgpt.store_interaction(prompt, text, session_id=session_id, user_id=user_id)
        add_user_memory(user_id, f"Q: {prompt}\nA: {text}")
        cache_answer(norm_prompt, text)
        return text

    # LLaMA first
    if engine == "llama" and LLAMA_HEALTHY:
        if debug_model_routing:
            return _dry_return("llama", model_name)
        result = await ask_llama(built_prompt, model_name)
        if not (isinstance(result, dict) and "error" in result):
            result_text = str(result).strip()
            if result_text and not _low_conf(result_text):
                if rec:
                    rec.engine_used = "llama"
                    rec.response = result_text
                    rec.model_name = model_name
                await append_history(prompt, "llama", result_text)
                await record("llama")
                memgpt.store_interaction(
                    prompt,
                    result_text,
                    session_id=session_id,
                    user_id=user_id,
                )
                add_user_memory(user_id, f"Q: {prompt}\nA: {result_text}")
                cache_answer(norm_prompt, result_text)
                logger.debug("LLaMA responded OK")
                return result_text

    # Fallback to GPT-4o
    if debug_model_routing:
        return _dry_return("gpt", "gpt-4o")
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
    memgpt.store_interaction(prompt, text, session_id=session_id, user_id=user_id)
    add_user_memory(user_id, f"Q: {prompt}\nA: {text}")
    cache_answer(norm_prompt, text)
    logger.debug("GPT responded OK with gpt-4o")
    return text


def _low_conf(resp: str) -> bool:
    import re

    if not resp.strip():
        return True
    if re.search(r"\b(i don't know|i am not sure|not sure|cannot help)\b", resp, re.I):
        return True
    return False
