"""Prompt‑routing layer for GesahniV2.

Responsible for:
* Intent detection & small‑talk short‑circuit
* Built‑in skill execution
* Home‑Assistant command handling
* Cache lookup / storage
* Delegating to GPT or LLaMA back‑ends (with override support)

Changes in this revision
-----------------------
1. **Safer model‑override logic** – key off `.startswith("gpt")` / `.startswith("llama")` and allow‑lists.
2. **Separate allow‑lists** – `ALLOWED_GPT_MODELS` and `ALLOWED_LLAMA_MODELS`.
3. **Early health‑check for LLaMA** – explicit 503 if unhealthy.
4. **Cleaner debug flag parsing** – boolean `debug_route`.
5. **Extra logging breadcrumbs** for easier tracing.
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
from .memory.vector_store import add_user_memory, cache_answer, lookup_cached_answer
from .model_picker import pick_model
from .prompt_builder import PromptBuilder
from .skills.base import SKILLS as BUILTIN_CATALOG, check_builtin_skills
from .skills.smalltalk_skill import SmalltalkSkill
from .telemetry import log_record_var
from .token_utils import count_tokens

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / Config
# ---------------------------------------------------------------------------
ALLOWED_GPT_MODELS: set[str] = set(
    os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(",")
)
ALLOWED_LLAMA_MODELS: set[str] = set(
    filter(None, os.getenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3").split(","))
)
CATALOG = BUILTIN_CATALOG  # allows tests to monkey‑patch
_SMALLTALK = SmalltalkSkill()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _low_conf(resp: str) -> bool:
    import re
    if not resp.strip():
        return True
    if re.search(r"\b(i don't know|i am not sure|not sure|cannot help)\b", resp, re.I):
        return True
    return False

# ---------------------------------------------------------------------------
# Main entry‑point
# ---------------------------------------------------------------------------
async def route_prompt(
    prompt: str,
    model_override: str | None = None,
    user_id: str = Depends(get_current_user_id),
) -> Any:
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

    # 1️⃣ Explicit override
    if model_override:
        mv = model_override.strip()
        logger.info("🔀 Model override requested → %s", mv)
        # GPT override
        if mv.startswith("gpt"):
            if mv not in ALLOWED_GPT_MODELS:
                raise HTTPException(status_code=400, detail=f"Model '{mv}' not allowed")
            if debug_route:
                return _dry("gpt", mv)
            return await _call_gpt_override(mv, prompt, norm_prompt, session_id, user_id, rec)
        # LLaMA override
        if mv.startswith("llama"):
            if ALLOWED_LLAMA_MODELS and mv not in ALLOWED_LLAMA_MODELS:
                raise HTTPException(status_code=400, detail=f"Model '{mv}' not allowed")
            if not LLAMA_HEALTHY:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="LLaMA backend unavailable")
            if debug_route:
                return _dry("llama", mv)
            return await _call_llama_override(mv, prompt, norm_prompt, session_id, user_id, rec)
        raise HTTPException(status_code=400, detail=f"Unknown or disallowed model '{mv}'")

    # 2️⃣ Built‑in skills
    if not skip_skills:
        for entry in CATALOG:
            if isinstance(entry, tuple) and len(entry) == 2:
                keywords, SkillClass = entry
                if any(kw in prompt for kw in keywords):
                    return await _run_skill(prompt, SkillClass, rec)
        skill_resp = await check_builtin_skills(prompt)
        if skill_resp is not None:
            return await _finalise("skill", prompt, skill_resp, rec)

    # 3️⃣ Home‑Assistant
    ha_resp = await handle_command(prompt)
    if ha_resp is not None:
        return await _finalise("ha", prompt, ha_resp.message, rec)

    # 4️⃣ Cache
    cached = lookup_cached_answer(norm_prompt)
    if cached is not None:
        if rec:
            rec.cache_hit = True
        return await _finalise("cache", prompt, cached, rec)

    # 5️⃣ Automatic selection
    engine, model_name = pick_model(prompt, intent, tokens)
    built_prompt, ptoks = PromptBuilder.build(
        prompt, session_id=session_id, user_id=user_id,
        custom_instructions=getattr(rec, "custom_instructions", ""),
        debug=debug_route, debug_info=getattr(rec, "debug_info", ""),
    )
    if rec:
        rec.prompt_tokens = ptoks

    if engine == "gpt":
        if debug_route:
            return _dry("gpt", model_name)
        return await _call_gpt(
            built_prompt=built_prompt, model=model_name,
            rec=rec, norm_prompt=norm_prompt,
            session_id=session_id, user_id=user_id, ptoks=ptoks
        )

    if engine == "llama" and LLAMA_HEALTHY:
        if debug_route:
            return _dry("llama", model_name)
        return await _call_llama(
            built_prompt=built_prompt, model=model_name,
            rec=rec, norm_prompt=norm_prompt,
            session_id=session_id, user_id=user_id, ptoks=ptoks
        )

    # Fallback GPT-4o
    if debug_route:
        return _dry("gpt", "gpt-4o")
    return await _call_gpt(
        built_prompt=built_prompt, model="gpt-4o",
        rec=rec, norm_prompt=norm_prompt,
        session_id=session_id, user_id=user_id, ptoks=ptoks
    )

# -------------------------------
# Override and helper routines
# -------------------------------
async def _call_gpt_override(model, prompt, norm_prompt, session_id, user_id, rec):
    built, pt = PromptBuilder.build(prompt, session_id=session_id, user_id=user_id)
    text, pt, ct, unit_price = await ask_gpt(built, model, SYSTEM_PROMPT)
    if rec:
        rec.engine_used = "gpt"
        rec.model_name = model
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = ((pt or 0) + (ct or 0)) / 1000 * unit_price
        rec.response = text
    await append_history(prompt, "gpt", text)
    await record("gpt", source="override")
    memgpt.store_interaction(prompt, text, session_id=session_id, user_id=user_id)
    add_user_memory(user_id, f"Q: {prompt}\nA: {text}")
    cache_answer(norm_prompt, text)
    return text

async def _call_llama_override(model, prompt, norm_prompt, session_id, user_id, rec):
    built, pt = PromptBuilder.build(prompt, session_id=session_id, user_id=user_id)
    result = await ask_llama(built, model)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(status_code=503, detail="LLaMA backend unavailable")
    result_text = str(result).strip()
    if not result_text or _low_conf(result_text):
        raise HTTPException(status_code=503, detail="Low-confidence LLaMA response")
    if rec:
        rec.engine_used = "llama"
        rec.model_name = model
        rec.prompt_tokens = pt
        rec.response = result_text
    await append_history(prompt, "llama", result_text)
    await record("llama", source="override")
    memgpt.store_interaction(prompt, result_text, session_id=session_id, user_id=user_id)
    add_user_memory(user_id, f"Q: {prompt}\nA: {result_text}")
    cache_answer(norm_prompt, result_text)
    return result_text

async def _run_skill(prompt: str, SkillClass, rec):
    skill_resp = await SkillClass().handle(prompt)
    return await _finalise("skill", prompt, str(skill_resp), rec)
