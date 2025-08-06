from __future__ import annotations

"""Prompt‑routing layer for GesahniV2.

Responsible for:
* Intent detection & small‑talk short‑circuit
* Built‑in skill execution
* Home‑Assistant command handling
* Cache lookup / storage
* Delegating to GPT or LLaMA back‑ends (with override support)

Changes in this revision
-----------------------
1. **Safer model‑override logic** – we now key off `.startswith("gpt")` / `startswith("llama")` instead of relying
   solely on an env list.   This prevents accidental mis‑routing when the env var is mis‑configured.
2. **Separate allow‑lists** – `ALLOWED_GPT_MODELS` and new `ALLOWED_LLAMA_MODELS` are exposed for tests.
3. **Early health‑check for LLaMA** – If the user explicitly requests a LLaMA model but the back‑end is unhealthy
   we raise an informative 503 instead of silently falling through to GPT.
4. **Cleaner debug flag parsing** – convert once to a boolean `debug_route`.
5. **Extra logging breadcrumbs** for easier tracing in production.
"""

import logging
import os
from typing import Any

from fastapi import Depends, HTTPException, status

from .analytics import record
from .deps.user import get_current_user_id
from .gpt_client import SYSTEM_PROMPT, ask_gpt
from .history import append_history
from .home_assistant import handle_command
from .intent_detector import detect_intent
from .llama_integration import LLAMA_HEALTHY, ask_llama
from .memory import memgpt
from .memory.vector_store import (
    add_user_memory,
    cache_answer,
    lookup_cached_answer,
)
from .model_picker import pick_model
from .prompt_builder import PromptBuilder
from .skills.base import SKILLS as BUILTIN_CATALOG, check_builtin_skills
from .skills.smalltalk_skill import SmalltalkSkill
from .telemetry import log_record_var
from .token_utils import count_tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
#                              Constants / Config
# ---------------------------------------------------------------------------

ALLOWED_GPT_MODELS: set[str] = set(
    os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(",")
)

# Expose a distinct allow‑list for LLaMA.  If unset we accept anything that
# starts with "llama" – useful in dev environments.
ALLOWED_LLAMA_MODELS: set[str] = set(
    filter(None, os.getenv("ALLOWED_LLAMA_MODELS", "").split(","))
)

CATALOG = BUILTIN_CATALOG  # allows tests to monkey‑patch
_SMALLTALK = SmalltalkSkill()

# ---------------------------------------------------------------------------
#                                  Helpers
# ---------------------------------------------------------------------------

def _low_conf(resp: str) -> bool:
    """Heuristic to detect uncertain answers from a model."""
    import re

    if not resp.strip():
        return True
    if re.search(r"\b(i don't know|i am not sure|not sure|cannot help)\b", resp, re.I):
        return True
    return False


# ---------------------------------------------------------------------------
#                                Main entry‑point
# ---------------------------------------------------------------------------

async def route_prompt(
    prompt: str,
    model_override: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> Any:
    """Route a prompt to the correct engine and return the answer."""

    # ── Telemetry object (may be *None* during unit tests) ──────────────────
    rec = log_record_var.get()

    norm_prompt = prompt.lower().strip()
    tokens = count_tokens(prompt)

    if rec:
        rec.prompt = prompt
        rec.embed_tokens = tokens
        rec.user_id = user_id

    session_id = rec.session_id if rec and rec.session_id else "default"

    debug_route = os.getenv("DEBUG_MODEL_ROUTING", "").lower() in {"1", "true", "yes"}

    def _dry(engine: str, model: str) -> str:
        msg = f"[dry-run] would call {engine} {model}"
        logger.info(msg)
        if rec:
            rec.engine_used = engine
            rec.model_name = model
            rec.response = msg
        return msg

    # -------------------------------------------------------------------
    # 1️⃣  Intent detection & small‑talk
    # -------------------------------------------------------------------
    intent, priority = detect_intent(prompt)
    if intent == "smalltalk":
        skill_resp = await _SMALLTALK.handle(prompt)
        if rec:
            rec.engine_used = "skill"
            rec.response = str(skill_resp)
        await append_history(prompt, "skill", str(skill_resp))
        await record("done", source="skill")
        return skill_resp

    skip_skills = intent == "chat" and priority == "high"

    # -------------------------------------------------------------------
    # 2️⃣  Explicit model override
    # -------------------------------------------------------------------
    if model_override:
        model_override = model_override.strip()
        logger.info("🔀 Model override requested → %s", model_override)

        if model_override.startswith("gpt") and model_override in ALLOWED_GPT_MODELS:
            built, ptoks = PromptBuilder.build(prompt, session_id=session_id, user_id=user_id)
            if debug_route:
                return _dry("gpt", model_override)
            return await _call_gpt(
                built_prompt=built,
                model=model_override,
                rec=rec,
                norm_prompt=norm_prompt,
                session_id=session_id,
                user_id=user_id,
                ptoks=ptoks,
            )

        if model_override.startswith("llama"):
            if ALLOWED_LLAMA_MODELS and model_override not in ALLOWED_LLAMA_MODELS:
                raise HTTPException(status_code=400, detail=f"Model '{model_override}' not allowed")
            if not LLAMA_HEALTHY:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLaMA backend unavailable")
            built, ptoks = PromptBuilder.build(prompt, session_id=session_id, user_id=user_id)
            if debug_route:
                return _dry("llama", model_override)
            return await _call_llama(
                built_prompt=built,
                model=model_override,
                rec=rec,
                norm_prompt=norm_prompt,
                session_id=session_id,
                user_id=user_id,
                ptoks=ptoks,
            )

        raise HTTPException(status_code=400, detail=f"Unknown or disallowed model '{model_override}'")

    # -------------------------------------------------------------------
    # 3️⃣  Skill catalogue (unless we intentionally skip)
    # -------------------------------------------------------------------
    if not skip_skills:
        for entry in CATALOG:
            if isinstance(entry, tuple) and len(entry) == 2:
                keywords, SkillClass = entry
                if any(kw in prompt for kw in keywords):
                    return await _run_skill(prompt, SkillClass, rec)
        skill_resp = await check_builtin_skills(prompt)
        if skill_resp is not None:
            return await _finalise("skill", prompt, skill_resp, rec)

    # -------------------------------------------------------------------
    # 4️⃣  Home‑Assistant commands
    # -------------------------------------------------------------------
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        return await _finalise("ha", prompt, ha_resp.message, rec)

    # -------------------------------------------------------------------
    # 5️⃣  Cache lookup
    # -------------------------------------------------------------------
    cached = lookup_cached_answer(norm_prompt)
    if cached is not None:
        if rec:
            rec.cache_hit = True
        return await _finalise("cache", prompt, cached, rec)

    # -------------------------------------------------------------------
    # 6️⃣  Automatic model selection
    # -------------------------------------------------------------------
    engine, model_name = pick_model(prompt, intent, tokens)
    built_prompt, ptoks = PromptBuilder.build(
        prompt,
        session_id=session_id,
        user_id=user_id,
        custom_instructions=getattr(rec, "custom_instructions", ""),
        debug=os.getenv("DEBUG", "").lower() in {"1", "true", "yes"},
        debug_info=getattr(rec, "debug_info", ""),
    )
    if rec:
        rec.prompt_tokens = ptoks

    # -- GPT path --------------------------------------------------------
    if engine == "gpt":
        if debug_route:
            return _dry("gpt", model_name)
        return await _call_gpt(
            built_prompt=built_prompt,
            model=model_name,
            rec=rec,
            norm_prompt=norm_prompt,
            session_id=session_id,
            user_id=user_id,
            ptoks=ptoks,
        )

    # -- LLaMA path ------------------------------------------------------
    if engine == "llama" and LLAMA_HEALTHY:
        if debug_route:
            return _dry("llama", model_name)
        return await _call_llama(
            built_prompt=built_prompt,
            model=model_name,
            rec=rec,
            norm_prompt=norm_prompt,
            session_id=session_id,
            user_id=user_id,
            ptoks=ptoks,
        )

    # -- Final fallback: GPT‑4o -----------------------------------------
    if debug_route:
        return _dry("gpt", "gpt-4o")
    return await _call_gpt(
        built_prompt=built_prompt,
        model="gpt-4o",
        rec=rec,
        norm_prompt=norm_prompt,
        session_id=session_id,
        user_id=user_id,
        ptoks=ptoks,
    )


# ---------------------------------------------------------------------------
#                         Internal helper sub‑routines
# ---------------------------------------------------------------------------

async def _run_skill(prompt: str, SkillClass, rec):
    skill_resp = await SkillClass().handle(prompt)
    return await _finalise("skill", prompt, str(skill_resp), rec)


async def _call_gpt(*, built_prompt: str, model: str, rec, norm_prompt: str, session_id: str, user_id: str, ptoks: int):
    text, pt, ct, unit_price = await ask_gpt(built_prompt, model, SYSTEM_PROMPT)
    return await _finalise(
        "gpt",
        prompt=norm_prompt,
        answer=text,
        rec=rec,
        model=model,
        pt=pt,
        ct=ct,
        unit_price=unit_price,
        session_id=session_id,
        user_id=user_id,
    )


async def _call_llama(*, built_prompt: str, model: str, rec, norm_prompt: str, session_id: str, user_id: str, ptoks: int):
    result = await ask_llama(built_prompt, model)
    # If result is an error dict, let caller fall through to fallback
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(result["error"])  # triggers GPT fallback

    result_text = str(result).strip()
    if not result_text or _low_conf(result_text):
        raise RuntimeError("low-confidence response")

    return await _finalise(
        "llama",
        prompt=norm_prompt,
        answer=result_text,
        rec=rec,
        model=model,
        session_id=session_id,
        user_id=user_id,
    )


async def _finalise(engine: str, prompt: str, answer: str, rec, *, model: str | None = None, pt: int | None = None, ct: int | None = None, unit_price: float | None = None, session_id: str | None = None, user_id: str | None = None):
    """Common bookkeeping for any successful reply."""
    await append_history(prompt, engine, answer)
    await record(engine)

    cache_answer(prompt, answer)
    add_user_memory(user_id, f"Q: {prompt}\nA: {answer}")
    memgpt.store_interaction(prompt, answer, session_id=session_id or "default", user_id=user_id)

    if rec:
        rec.engine_used = engine
        rec.response = answer
        rec.model_name = model or rec.model_name
        rec.prompt_tokens = pt or rec.prompt_tokens
        rec.completion_tokens = ct or rec.completion_tokens
        if pt and ct and unit_price:
            rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * unit_price

    logger.debug("%s responded OK", engine.upper())
    return answer
