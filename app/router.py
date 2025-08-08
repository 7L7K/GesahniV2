import logging
import os
import inspect
from typing import Any, Awaitable, Callable

from fastapi import Depends, HTTPException, status

from .analytics import record
from .deps.user import get_current_user_id
from .gpt_client import SYSTEM_PROMPT, ask_gpt
from .history import append_history
from .home_assistant import handle_command
from .intent_detector import detect_intent
import app.llama_integration as llama_integration
from .llama_integration import ask_llama

try:  # pragma: no cover - fall back if circuit flag missing
    from .llama_integration import llama_circuit_open  # type: ignore
except Exception:  # pragma: no cover - defensive
    llama_circuit_open = False  # type: ignore
from .memory import memgpt
from .memory.vector_store import add_user_memory, cache_answer, lookup_cached_answer
from .model_picker import pick_model
from . import model_picker as model_picker_module
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
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
    **gen_opts: Any,
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

    # Circuit breaker check: degrade to GPT if LLaMA is unavailable
    if llama_circuit_open:
        llama_integration.LLAMA_HEALTHY = False
        # keep model picker in sync so GPT is selected
        model_picker_module.LLAMA_HEALTHY = False

    intent, priority = detect_intent(prompt)

    # 1️⃣ Explicit override (bypass skills like smalltalk)
    if model_override:
        mv = model_override.strip()
        logger.info("🔀 Model override requested → %s", mv)
        # GPT override
        if mv.startswith("gpt"):
            if mv not in ALLOWED_GPT_MODELS:
                raise HTTPException(status_code=400, detail=f"Model '{mv}' not allowed")
            if debug_route:
                return _dry("gpt", mv)
            try:
                return await _call_gpt_override(
                    mv, prompt, norm_prompt, session_id, user_id, rec, stream_cb
                )
            except Exception as e:
                logger.warning("GPT override failed: %s", e)
                if llama_integration.LLAMA_HEALTHY:
                    fallback_built, fallback_pt = PromptBuilder.build(
                        prompt,
                        session_id=session_id,
                        user_id=user_id,
                        **gen_opts,
                    )
                    fallback_model = os.getenv("OLLAMA_MODEL", "llama3")
                    return await _call_llama(
                        prompt=prompt,
                        built_prompt=fallback_built,
                        model=fallback_model,
                        rec=rec,
                        norm_prompt=norm_prompt,
                        session_id=session_id,
                        user_id=user_id,
                        ptoks=fallback_pt,
                        stream_cb=stream_cb,
                        gen_opts=gen_opts,
                    )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="GPT backend unavailable",
                )
        # LLaMA override
        if mv.startswith("llama"):
            if ALLOWED_LLAMA_MODELS and mv not in ALLOWED_LLAMA_MODELS:
                raise HTTPException(status_code=400, detail=f"Model '{mv}' not allowed")
            if not llama_integration.LLAMA_HEALTHY:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="LLaMA backend unavailable",
                )
            if debug_route:
                return _dry("llama", mv)
            return await _call_llama_override(
                mv,
                prompt,
                norm_prompt,
                session_id,
                user_id,
                rec,
                stream_cb,
                gen_opts,
            )
        raise HTTPException(
            status_code=400, detail=f"Unknown or disallowed model '{mv}'"
        )

    # Cache check should happen before smalltalk so cached answers short‑circuit
    cached = lookup_cached_answer(norm_prompt)
    if cached is not None:
        if rec:
            rec.cache_hit = True
        return await _finalise("cache", prompt, cached, rec)

    if intent == "smalltalk":
        try:
            skill_resp = await _SMALLTALK.handle(prompt)
        except Exception:
            skill_resp = None
        if skill_resp is not None:
            if rec:
                rec.engine_used = "skill"
                rec.response = str(skill_resp)
            await append_history(prompt, "skill", str(skill_resp))
            await record("done", source="skill")
            return skill_resp

    skip_skills = intent == "chat" and priority == "high"

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
    ha_resp = handle_command(prompt)
    if inspect.isawaitable(ha_resp):
        ha_resp = await ha_resp
    if ha_resp is not None:
        return await _finalise("ha", prompt, ha_resp.message, rec)

    # 4️⃣ Cache (secondary check in case routing above changed state)
    cached = lookup_cached_answer(norm_prompt)
    if cached is not None:
        if rec:
            rec.cache_hit = True
        return await _finalise("cache", prompt, cached, rec)

    # 5️⃣ Automatic selection
    engine, model_name = pick_model(prompt, intent, tokens)
    built_prompt, ptoks = PromptBuilder.build(
        prompt,
        session_id=session_id,
        user_id=user_id,
        custom_instructions=getattr(rec, "custom_instructions", ""),
        debug=debug_route,
        debug_info=getattr(rec, "debug_info", ""),
        **gen_opts,
    )
    if rec:
        rec.prompt_tokens = ptoks

    if engine == "gpt":
        if debug_route:
            return _dry("gpt", model_name)
        try:
            return await _call_gpt(
                prompt=prompt,
                built_prompt=built_prompt,
                model=model_name,
                rec=rec,
                norm_prompt=norm_prompt,
                session_id=session_id,
                user_id=user_id,
                ptoks=ptoks,
                stream_cb=stream_cb,
            )
        except Exception as e:
            logger.warning("GPT call failed: %s", e)
            if llama_integration.LLAMA_HEALTHY:
                fallback_model = os.getenv("OLLAMA_MODEL", "llama3")
                return await _call_llama(
                    prompt=prompt,
                    built_prompt=built_prompt,
                    model=fallback_model,
                    rec=rec,
                    norm_prompt=norm_prompt,
                    session_id=session_id,
                    user_id=user_id,
                    ptoks=ptoks,
                    stream_cb=stream_cb,
                )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GPT backend unavailable",
            )

    if engine == "llama" and llama_integration.LLAMA_HEALTHY:
        if debug_route:
            return _dry("llama", model_name)
        return await _call_llama(
            prompt=prompt,
            built_prompt=built_prompt,
            model=model_name,
            rec=rec,
            norm_prompt=norm_prompt,
            session_id=session_id,
            user_id=user_id,
            ptoks=ptoks,
            stream_cb=stream_cb,
            gen_opts=gen_opts,
        )

    # Fallback GPT-4o
    if debug_route:
        return _dry("gpt", "gpt-4o")
    try:
        return await _call_gpt(
            prompt=prompt,
            built_prompt=built_prompt,
            model="gpt-4o",
            rec=rec,
            norm_prompt=norm_prompt,
            session_id=session_id,
            user_id=user_id,
            ptoks=ptoks,
            stream_cb=stream_cb,
        )
    except Exception as e:
        logger.warning("GPT fallback failed: %s", e)
        if llama_integration.LLAMA_HEALTHY:
            fallback_model = os.getenv("OLLAMA_MODEL", "llama3")
            return await _call_llama(
                prompt=prompt,
                built_prompt=built_prompt,
                model=fallback_model,
                rec=rec,
                norm_prompt=norm_prompt,
                session_id=session_id,
                user_id=user_id,
                ptoks=ptoks,
                stream_cb=stream_cb,
                gen_opts=gen_opts,
            )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GPT backend unavailable",
        )


# -------------------------------
# Override and helper routines
# -------------------------------
async def _call_gpt_override(
    model,
    prompt,
    norm_prompt,
    session_id,
    user_id,
    rec,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
):
    built, pt = PromptBuilder.build(prompt, session_id=session_id, user_id=user_id)
    try:
        text, pt, ct, cost = await ask_gpt(
            built, model, SYSTEM_PROMPT, stream=bool(stream_cb), on_token=stream_cb
        )
    except TypeError:
        text, pt, ct, cost = await ask_gpt(built, model, SYSTEM_PROMPT)
    if rec:
        rec.engine_used = "gpt"
        rec.model_name = model
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = cost
        rec.response = text
    await append_history(prompt, "gpt", text)
    await record("gpt", source="override")
    memgpt.store_interaction(prompt, text, session_id=session_id, user_id=user_id)
    add_user_memory(user_id, f"Q: {prompt}\nA: {text}")
    try:
        cache_answer(prompt=norm_prompt, answer=text)
    except Exception as e:  # pragma: no cover
        logger.warning("QA cache store failed (gpt override): %s", e)
    return text


async def _call_llama_override(
    model,
    prompt,
    norm_prompt,
    session_id,
    user_id,
    rec,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
    gen_opts: dict[str, Any] | None = None,
):
    built, pt = PromptBuilder.build(
        prompt, session_id=session_id, user_id=user_id, **(gen_opts or {})
    )
    tokens: list[str] = []
    logger.debug(
        "LLaMA override opts: temperature=%s top_p=%s",
        (gen_opts or {}).get("temperature"),
        (gen_opts or {}).get("top_p"),
    )
    try:
        async for tok in ask_llama(built, model, **(gen_opts or {})):
            tokens.append(tok)
            if stream_cb:
                await stream_cb(tok)
    except Exception:
        raise HTTPException(status_code=503, detail="LLaMA backend unavailable")
    result_text = "".join(tokens).strip()
    if not result_text or _low_conf(result_text):
        raise HTTPException(status_code=503, detail="Low-confidence LLaMA response")
    if rec:
        rec.engine_used = "llama"
        rec.model_name = model
        rec.prompt_tokens = pt
        rec.response = result_text
    await append_history(prompt, "llama", result_text)
    await record("llama", source="override")
    memgpt.store_interaction(
        prompt, result_text, session_id=session_id, user_id=user_id
    )
    add_user_memory(user_id, f"Q: {prompt}\nA: {result_text}")
    try:
        cache_answer(prompt=norm_prompt, answer=result_text)
    except Exception as e:  # pragma: no cover
        logger.warning("QA cache store failed (llama override): %s", e)
    return result_text


async def _call_gpt(
    *,
    prompt: str,
    built_prompt: str,
    model: str,
    rec,
    norm_prompt: str,
    session_id: str,
    user_id: str,
    ptoks: int,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
):
    try:
        text, pt, ct, cost = await ask_gpt(
            built_prompt,
            model,
            SYSTEM_PROMPT,
            stream=bool(stream_cb),
            on_token=stream_cb,
        )
    except TypeError:
        text, pt, ct, cost = await ask_gpt(built_prompt, model, SYSTEM_PROMPT)
    if rec:
        rec.engine_used = "gpt"
        rec.model_name = model
        rec.prompt_tokens = pt
        rec.completion_tokens = ct
        rec.cost_usd = cost
        rec.response = text
    memgpt.store_interaction(prompt, text, session_id=session_id, user_id=user_id)
    add_user_memory(user_id, f"Q: {prompt}\nA: {text}")
    try:
        cache_answer(prompt=norm_prompt, answer=text)
    except Exception as e:  # pragma: no cover
        logger.warning("QA cache store failed (gpt): %s", e)
    return await _finalise("gpt", prompt, text, rec)


async def _call_llama(
    *,
    prompt: str,
    built_prompt: str,
    model: str,
    rec,
    norm_prompt: str,
    session_id: str,
    user_id: str,
    ptoks: int,
    stream_cb: Callable[[str], Awaitable[None]] | None = None,
    gen_opts: dict[str, Any] | None = None,
):
    tokens: list[str] = []
    logger.debug(
        "LLaMA opts: temperature=%s top_p=%s",
        (gen_opts or {}).get("temperature"),
        (gen_opts or {}).get("top_p"),
    )
    try:
        result = ask_llama(built_prompt, model, **(gen_opts or {}))
        if inspect.isasyncgen(result):
            async for tok in result:
                tokens.append(tok)
                if stream_cb:
                    await stream_cb(tok)
            result_text = "".join(tokens).strip()
        else:
            if inspect.isawaitable(result):
                result = await result
            if isinstance(result, dict) and result.get("error"):
                raise RuntimeError(str(result.get("error")))
            result_text = (result or "").strip()
    except Exception:
        fallback_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        text = await _call_gpt(
            prompt=prompt,
            built_prompt=built_prompt,
            model=fallback_model,
            rec=rec,
            norm_prompt=norm_prompt,
            session_id=session_id,
            user_id=user_id,
            ptoks=ptoks,
            stream_cb=stream_cb,
        )
        await record("gpt", fallback=True)
        return text
    if not result_text or _low_conf(result_text):
        raise HTTPException(status_code=503, detail="Low-confidence LLaMA response")
    if rec:
        rec.engine_used = "llama"
        rec.model_name = model
        rec.prompt_tokens = ptoks
        rec.response = result_text
    memgpt.store_interaction(
        prompt, result_text, session_id=session_id, user_id=user_id
    )
    add_user_memory(user_id, f"Q: {prompt}\nA: {result_text}")
    try:
        cache_answer(prompt=norm_prompt, answer=result_text)
    except Exception as e:  # pragma: no cover
        logger.warning("QA cache store failed (llama): %s", e)
    return await _finalise("llama", prompt, result_text, rec)


async def _finalise(engine: str, prompt: str, text: str, rec):
    if rec:
        rec.engine_used = engine
        rec.response = text
    await append_history(prompt, engine, text)
    await record(engine)
    return text


async def _run_skill(prompt: str, SkillClass, rec):
    skill_resp = await SkillClass().handle(prompt)
    return await _finalise("skill", prompt, str(skill_resp), rec)
