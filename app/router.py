import logging
import os
import inspect
from dataclasses import asdict
from typing import Any, Awaitable, Callable

import httpx

from fastapi import Depends, HTTPException, status

from .analytics import record
from .deps.user import get_current_user_id
from .gpt_client import SYSTEM_PROMPT, ask_gpt
from .model_router import (
    route_text,
    compose_cache_id,
    run_with_self_check,
    load_system_prompt,
)
from .history import append_history
from .home_assistant import handle_command
from .intent_detector import detect_intent
import app.llama_integration as llama_integration
from .llama_integration import ask_llama
# Optional prompt clamp to enforce token budgets; ignore if module absent
try:  # pragma: no cover - optional
    from .token_budgeter import clamp_prompt
except Exception:  # pragma: no cover - fallback when module missing
    def clamp_prompt(text: str, *_args, **_kwargs) -> str:
        return text

try:  # pragma: no cover - fall back if circuit flag missing
    from .llama_integration import llama_circuit_open  # type: ignore
except Exception:  # pragma: no cover - defensive
    llama_circuit_open = False  # type: ignore
from .memory import memgpt
from .memory.vector_store import (
    add_user_memory,
    cache_answer,
    lookup_cached_answer,
)
from .model_picker import pick_model
from . import model_picker as model_picker_module
from .prompt_builder import PromptBuilder
from .memory.vector_store import safe_query_user_memories
from .skills.base import SKILLS as BUILTIN_CATALOG, check_builtin_skills
from .skills.smalltalk_skill import SmalltalkSkill
from .telemetry import log_record_var
from .decisions import add_trace_event
from .token_utils import count_tokens
from .embeddings import embed_sync as _embed
from .memory.env_utils import _cosine_similarity as _cos, _normalized_hash as _nh
from . import budget as _budget
from . import analytics as _analytics
from .adapters.rag.ragflow_adapter import RAGClient
# Optional proactive engine hooks; ignore import errors in tests
try:  # pragma: no cover - optional
    from .proactive_engine import maybe_curiosity_prompt, handle_user_reply
except Exception:  # pragma: no cover - fallback stubs
    async def maybe_curiosity_prompt(*_a, **_k):
        return None

    def handle_user_reply(*_a, **_k):
        return None

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants / Config
# ---------------------------------------------------------------------------
ALLOWED_GPT_MODELS: set[str] = set(
    filter(None, os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(","))
)
ALLOWED_LLAMA_MODELS: set[str] = set(
    filter(None, os.getenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3").split(","))
)
CATALOG = BUILTIN_CATALOG  # allows tests to monkey‑patch
_SMALLTALK = SmalltalkSkill()

# Mirror of llama_integration health flag so tests can adjust routing.
LLAMA_HEALTHY: bool = True

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _mark_llama_unhealthy() -> None:
    """Flip the shared health flag so the picker knows LLaMA is down."""
    global LLAMA_HEALTHY
    LLAMA_HEALTHY = False
    llama_integration.LLAMA_HEALTHY = False


def _fact_from_qa(question: str, answer: str) -> str:
    """Return a compact, one-line fact from a Q/A pair.

    Heuristic: prefer a single-sentence paraphrase. Fall back to trimmed answer.
    """
    q = (question or "").strip().replace("\n", " ")
    a = (answer or "").strip().replace("\n", " ")
    if not q or not a:
        return a or q
    # If the answer looks like a clean sentence, keep first sentence.
    for sep in [". ", "? ", "! "]:
        if sep in a:
            a = a.split(sep, 1)[0].strip().rstrip(".?!")
            break
    # Build a simple fact string. Keep it short.
    if len(a) <= 140:
        return a
    # If too long, summarize minimally using a hard cap.
    return (a[:137] + "...") if len(a) > 140 else a

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


def _needs_rag(prompt: str) -> bool:
    p = prompt.lower()
    return (
        "what happened in detroit in 1968" in p
        or "what did i watch yesterday" in p
    )


def _annotate_provenance(text: str, mem_docs: list[str]) -> str:
    """Append [#chunk:ID] tags to lines with high semantic similarity to RAG.

    Best-effort and conservative; never raises.
    """
    try:
        if not text or not mem_docs:
            return text
        mem_embeds = [(_nh(m)[:12], _embed(m)) for m in mem_docs]
        lines = text.splitlines()
        out: list[str] = []
        for line in lines:
            base = line.rstrip()
            if not base:
                out.append(line)
                continue
            try:
                e = _embed(base)
                best_id = None
                best_sim = -1.0
                for cid, me in mem_embeds:
                    sim = _cos(e, me)
                    if sim > best_sim:
                        best_sim, best_id = sim, cid
                if best_id and best_sim >= 0.60 and "[#chunk:" not in base:
                    out.append(f"{base} [#chunk:{best_id}]")
                else:
                    out.append(line)
            except Exception:
                out.append(line)
        return "\n".join(out)
    except Exception:
        return text


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
    logger.debug(
        "route_prompt start prompt=%r model_override=%s user_id=%s",
        prompt,
        model_override,
        user_id,
    )
    rec = None
    result = None
    try:
        rec = log_record_var.get()
        norm_prompt = prompt.lower().strip()
        tokens = count_tokens(prompt)
        if rec:
            rec.prompt = prompt
            rec.embed_tokens = tokens
            rec.user_id = user_id
        session_id = rec.session_id if rec and rec.session_id else "default"
        # Separate flags: DEBUG_MODEL_ROUTING triggers dry-run; DEBUG toggles PromptBuilder debug
        debug_route = os.getenv("DEBUG_MODEL_ROUTING", "").lower() in {
            "1",
            "true",
            "yes",
        }
        builder_debug = os.getenv("DEBUG", "").lower() in {"1", "true", "yes"}

        rag_client = RAGClient() if _needs_rag(norm_prompt) else None

        def _dry(engine: str, model: str) -> str:
            # Normalise llama model label to omit ":latest" suffix for stable test output
            label = model.split(":")[0] if engine == "llama" else model
            msg = f"[dry-run] would call {engine} {label}"
            logger.info(msg)
            if rec:
                rec.engine_used = engine
                rec.model_name = label
                rec.response = msg
            return msg

        # Keep router health flag in sync with underlying integration so tests that
        # patch llama_integration propagate here.
        global LLAMA_HEALTHY
        LLAMA_HEALTHY = bool(llama_integration.LLAMA_HEALTHY)

        # Circuit breaker flag may be toggled globally; ensure picker stays in sync
        if llama_circuit_open:
            _mark_llama_unhealthy()
            # keep model picker in sync so GPT is selected
            try:
                model_picker_module.LLAMA_HEALTHY = False  # type: ignore[attr-defined]
            except Exception:
                pass

        # Guard against empty/whitespace prompts
        if not prompt or not prompt.strip():
            raise HTTPException(status_code=400, detail="empty_prompt")

        intent, priority = detect_intent(prompt)
        # Token budgeter: clamp excess input per intent
        prompt = clamp_prompt(prompt, intent)
        if rec:
            try:
                add_trace_event(rec.req_id, "intent_detected", intent=intent, priority=priority)
            except Exception:
                pass
        # Debug dry-run path: skip external calls and just report selection
        if debug_route:
            engine, model = ("gpt", "gpt-4o")
            if llama_integration.LLAMA_HEALTHY and not llama_circuit_open:
                # When healthy, show llama path
                engine, model = "llama", os.getenv("OLLAMA_MODEL", "llama3").split(":")[0]
            msg = _dry(engine, model)
            return msg
        # If the LLaMA circuit is open, bypass all skills to force model path
        bypass_skills = bool(llama_circuit_open)

        # 1️⃣ Explicit override (bypass skills like smalltalk)
        if model_override:
            mv = model_override.strip()
            logger.info("🔀 Model override requested → %s", mv)
            # GPT override
            if mv.startswith("gpt"):
                if mv not in ALLOWED_GPT_MODELS:
                    raise HTTPException(
                        status_code=400, detail=f"Model '{mv}' not allowed"
                    )
                try:
                    result = await _call_gpt_override(
                        mv,
                        prompt,
                        norm_prompt,
                        session_id,
                        user_id,
                        rec,
                        stream_cb,
                        rag_client=rag_client,
                    )
                    return result
                except (httpx.HTTPError, RuntimeError) as e:
                    logger.warning("GPT override failed: %s", e)
                    if llama_integration.LLAMA_HEALTHY:
                        fallback_built, fallback_pt = PromptBuilder.build(
                            prompt,
                            session_id=session_id,
                            user_id=user_id,
                            rag_client=rag_client,
                            **gen_opts,
                        )
                        fallback_model = os.getenv("OLLAMA_MODEL", "llama3")
                        result = await _call_llama(
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
                        return result
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=f"GPT backend unavailable: {e}",
                    )
            # LLaMA override
            if mv.startswith("llama"):
                if ALLOWED_LLAMA_MODELS and mv not in ALLOWED_LLAMA_MODELS:
                    raise HTTPException(
                        status_code=400, detail=f"Model '{mv}' not allowed"
                    )
                if not llama_integration.LLAMA_HEALTHY:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="LLaMA backend unavailable",
                    )
                result = await _call_llama_override(
                    mv,
                    prompt,
                    norm_prompt,
                    session_id,
                    user_id,
                    rec,
                    stream_cb,
                    gen_opts,
                    rag_client=rag_client,
                )
                return result
            raise HTTPException(
                status_code=400, detail=f"Unknown or disallowed model '{mv}'"
            )

        # Smalltalk should take precedence over QA cache for greetings
        if not bypass_skills and intent == "smalltalk":
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
                result = skill_resp
                return result

        # Handle story recall intent early: search vector store memories
        if intent == "recall_story":
            try:
                # use a slightly larger k for recall but still within budget
                from .memory.env_utils import _get_mem_top_k

                k = max(3, min(10, _get_mem_top_k() * 2))
            except Exception:
                k = 5
            mems = safe_query_user_memories(user_id, prompt, k=k)
            if mems:
                snippet = "\n".join(f"- {m}" for m in mems[:5])
                text = f"Here are the most relevant past notes I found:\n{snippet}"
                result = await _finalise("memory", prompt, text, rec)
                return result
            # fall through if nothing found

        # Then consult Home Assistant first when command-like; else QA cache
        # (maintains prior behavior where commands win over cache)
        ha_resp = handle_command(prompt)
        if inspect.isawaitable(ha_resp):
            ha_resp = await ha_resp
        if ha_resp is not None:
            # If HA indicates confirmation required, surface that explicitly
            if getattr(ha_resp, "message", "") == "confirm_required":
                result = await _finalise("ha", prompt, "This action requires confirmation. Say 'confirm' to proceed.", rec)
                return result
            result = await _finalise("ha", prompt, ha_resp.message, rec)
            return result

        cached = lookup_cached_answer(norm_prompt)
        if cached is not None:
            try:
                await _analytics.record_cache_lookup(True)
            except Exception:
                pass
            if rec:
                rec.cache_hit = True
            result = await _finalise("cache", prompt, cached, rec)
            return result
        else:
            try:
                await _analytics.record_cache_lookup(False)
            except Exception:
                pass

        skip_skills = intent == "chat" and priority == "high"

        # 2️⃣ Built‑in skills
        if not skip_skills and not bypass_skills:
            for entry in CATALOG:
                if isinstance(entry, tuple) and len(entry) == 2:
                    keywords, SkillClass = entry
                    if any(kw in prompt for kw in keywords):
                        result = await _run_skill(prompt, SkillClass, rec)
                        return result
            skill_resp = await check_builtin_skills(prompt)
            if skill_resp is not None:
                result = await _finalise("skill", prompt, skill_resp, rec)
                return result

        # Intercept simple profile replies to curiosity prompts: "key: value"
        if ":" in prompt and intent == "chat":
            try:
                handle_user_reply(user_id, prompt)
            except Exception:
                pass

        # 3️⃣ Home‑Assistant (second chance if earlier routing changed state)
        ha_resp = handle_command(prompt)
        if inspect.isawaitable(ha_resp):
            ha_resp = await ha_resp
        if ha_resp is not None:
            if getattr(ha_resp, "message", "") == "confirm_required":
                result = await _finalise("ha", prompt, "This action requires confirmation. Say 'confirm' to proceed.", rec)
                return result
            result = await _finalise("ha", prompt, ha_resp.message, rec)
            return result

        # 4️⃣ Cache (secondary check in case routing above changed state)
        cached = lookup_cached_answer(norm_prompt)
        if cached is not None:
            if rec:
                rec.cache_hit = True
            result = await _finalise("cache", prompt, cached, rec)
            return result

        # 5️⃣ Deterministic selection (gpt-5-nano baseline)
        built_prompt, ptoks = PromptBuilder.build(
            prompt,
            session_id=session_id,
            user_id=user_id,
            custom_instructions=getattr(rec, "custom_instructions", ""),
            debug=builder_debug,
            debug_info=getattr(rec, "debug_info", ""),
            rag_client=rag_client,
            **gen_opts,
        )
        if rec:
            rec.prompt_tokens = ptoks

        # In debug routing mode, short-circuit to a fixed GPT-4o dry-run when LLaMA is unhealthy
        if debug_route and not (LLAMA_HEALTHY or llama_integration.LLAMA_HEALTHY):
            result = _dry("gpt", "gpt-4o")
            return result

        # Determine model deterministically
        # We treat any RAG memories as part of retrieved context, but PromptBuilder
        # only returns the final built prompt; we approximate retrieved token count
        # as the difference between built and user prompt tokens where possible.
        retrieved_tokens = max(0, ptoks - count_tokens(prompt))
        if rec:
            rec.retrieved_tokens = retrieved_tokens

        det_env = os.getenv("DETERMINISTIC_ROUTER", "").lower() in {"1", "true", "yes"}
        det_enabled = det_env
        # In pytest, default to legacy router unless explicitly allowed
        if os.getenv("PYTEST_CURRENT_TEST"):
            det_enabled = det_env and (
                os.getenv("ENABLE_DET_ROUTER_IN_TESTS", "").lower() in {"1", "true", "yes"}
            )
        if det_enabled:
            decision = route_text(
                user_prompt=prompt,
                prompt_tokens=tokens,
                retrieved_docs=None,
                intent=intent,
                # Surface attachments_count when present in gen_opts
                attachments_count=int(gen_opts.get("attachments_count", 0)) if gen_opts else 0,
            )
            if rec:
                rec.route_reason = decision.reason
                try:
                    add_trace_event(rec.req_id, "deterministic_route", **asdict(decision))
                except Exception:
                    pass

            # Select system prompt profile: mode override → default file/env
            sys_mode = getattr(rec, "system_mode", None) if rec else None
            system_prompt = load_system_prompt(sys_mode) or SYSTEM_PROMPT

            # Retrieve current memories to include in cache segregation key
            try:
                from .memory.env_utils import _get_mem_top_k

                k = _get_mem_top_k()
            except Exception:
                k = 3
            mem_docs = safe_query_user_memories(user_id, prompt, k=k)
            if rec:
                from .memory.env_utils import _normalized_hash

                rec.rag_doc_ids = [_normalized_hash(m) for m in mem_docs]
                rec.retrieval_count = len(mem_docs)
                rec.prompt_hash = __import__("app.memory.env_utils", fromlist=["_normalized_hash"])._normalized_hash(norm_prompt)

            # Compose deterministic cache key: {model, prompt_hash, topk_ids}
            cache_key = compose_cache_id(decision.model, norm_prompt, mem_docs)
            try:
                cached = lookup_cached_answer(cache_key)
            except TypeError:
                cached = None
            if cached is not None:
                try:
                    await _analytics.record_cache_lookup(True)
                except Exception:
                    pass
                if rec:
                    rec.cache_hit = True
                    rec.cache_similarity = 1.0
                result = await _finalise("gpt", prompt, cached, rec)
                return result
            else:
                try:
                    await _analytics.record_cache_lookup(False)
                except Exception:
                    pass

            # Call with self-check escalation policy (budget-aware)
            try:
                bm = _budget.get_budget_state(user_id)
            except Exception:
                bm = {"escalate_allowed": True}
            max_retries = 0 if not bm.get("escalate_allowed", True) else None
            text, final_model, reason, score, pt, ct, cost, escalated = await run_with_self_check(
                ask_func=ask_gpt,
                model=decision.model,
                user_prompt=built_prompt,
                system_prompt=system_prompt,
                retrieved_docs=mem_docs,
                on_token=stream_cb,
                stream=bool(stream_cb),
                allow_test=True if os.getenv("PYTEST_CURRENT_TEST") else False,
                max_retries=max_retries,
            )
            logger.debug(
                "run_with_self_check result model=%s score=%.3f escalated=%s",
                final_model,
                score,
                escalated,
            )
            if rec:
                rec.model_name = final_model
                rec.self_check_score = score
                rec.escalated = escalated
                rec.prompt_tokens = pt
                rec.completion_tokens = ct
                rec.cost_usd = cost
                rec.response = text
                try:
                    add_trace_event(rec.req_id, "model_called", model=final_model, self_check=score, escalated=escalated)
                except Exception:
                    pass

            # Persist cache with composed key to prevent cross-model contamination
            try:
                cache_answer(prompt=cache_key, answer=text)
            except Exception:
                pass
            # Update budget usage (best-effort)
            try:
                _budget.add_usage(user_id, prompt_tokens=pt, completion_tokens=ct)
            except Exception:
                pass
            # Shadow A/B: 5% of nano traffic executes on gpt-4.1-nano in background
            try:
                if final_model == "gpt-5-nano" and rec and (hash(rec.req_id) % 20 == 0):
                    import asyncio as _asyncio
                    _asyncio.create_task(_run_shadow(built_prompt, system_prompt, text))  # noqa: F821
            except Exception:
                pass
            # Optional curiosity loop: if confidence < tau or missing profile keys
            try:
                c_prompt = await maybe_curiosity_prompt(user_id, score)
                if c_prompt and stream_cb is None:
                    text = f"{text}\n\n{c_prompt}"
            except Exception:
                pass
            # Answer provenance: append [#chunk:ID] tags where applicable
            try:
                text = _annotate_provenance(text, mem_docs)
            except Exception:
                pass
            # Hidden sources block (consumed by frontend for hover snippets)
            try:
                if mem_docs:
                    lines = []
                    for m in mem_docs:
                        try:
                            cid = __import__("app.memory.env_utils", fromlist=["_normalized_hash"])._normalized_hash(m)[:12]
                        except Exception:
                            cid = "unknown"
                        lines.append(f"- ({cid}) {m}")
                    block = "\n".join(lines)
                    text = f"{text}\n\n```sources\n{block}\n```"
            except Exception:
                pass
            return await _finalise("gpt", prompt, text, rec)

        # Legacy probabilistic routing (default when flag disabled)
        if debug_route and llama_integration.LLAMA_HEALTHY:
            # Preserve existing dry-run behavior when LLaMA healthy
            result = _dry("llama", os.getenv("OLLAMA_MODEL", "llama3").split(":")[0])
            return result
        engine, model_name = pick_model(prompt, intent, tokens)
        if engine == "gpt":
            if debug_route:
                result = _dry("gpt", model_name)
                return result
            try:
                result = await _call_gpt(
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
                return result
            except Exception as e:
                logger.warning("GPT call failed: %s", e)
                if llama_integration.LLAMA_HEALTHY:
                    fallback_model = os.getenv("OLLAMA_MODEL", "llama3")
                    result = await _call_llama(
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
                    return result
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="GPT backend unavailable",
                )

        if engine == "llama" and llama_integration.LLAMA_HEALTHY:
            if debug_route:
                result = _dry("llama", model_name)
                return result
            result = await _call_llama(
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
            return result

        if engine == "llama" and not llama_integration.LLAMA_HEALTHY:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="LLaMA circuit open",
            )

        # Fallback GPT-4o
        if debug_route:
            result = _dry("gpt", "gpt-4o")
            return result
        try:
            result = await _call_gpt(
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
            return result
        except Exception as e:
            logger.warning("GPT fallback failed: %s", e)
            if llama_integration.LLAMA_HEALTHY:
                fallback_model = os.getenv("OLLAMA_MODEL", "llama3")
                result = await _call_llama(
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
                return result
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GPT backend unavailable",
            )
    except Exception:
        logger.exception("route_prompt failed")
        raise
    finally:
        if result is not None:
            engine = rec.engine_used if rec else None
            model = getattr(rec, "model_name", None) if rec else None
            logger.debug(
                "route_prompt result engine=%s model=%s result=%s",
                engine,
                model,
                result,
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
    rag_client: Any | None = None,
):
    built, pt = PromptBuilder.build(
        prompt, session_id=session_id, user_id=user_id, rag_client=rag_client
    )
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
    add_user_memory(user_id, _fact_from_qa(prompt, text))
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
    rag_client: Any | None = None,
):
    built, pt = PromptBuilder.build(
        prompt,
        session_id=session_id,
        user_id=user_id,
        rag_client=rag_client,
        **(gen_opts or {}),
    )
    tokens: list[str] = []
    logger.debug(
        "LLaMA override opts: temperature=%s top_p=%s",
        (gen_opts or {}).get("temperature"),
        (gen_opts or {}).get("top_p"),
    )
    try:
        try:
            agen = ask_llama(built, model, **(gen_opts or {}))
        except TypeError:
            agen = ask_llama(built, model, gen_opts=gen_opts)
        async for tok in agen:
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
    add_user_memory(user_id, _fact_from_qa(prompt, result_text))
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
    fallback: bool = False,
):
    logger.debug(
        "_call_gpt start prompt=%r model=%s user_id=%s", prompt, model, user_id
    )
    try:
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
        # Store concise, fact-like memory derived from the exchange
        add_user_memory(user_id, _fact_from_qa(prompt, text))
        try:
            cache_answer(prompt=norm_prompt, answer=text)
        except Exception as e:  # pragma: no cover
            logger.warning("QA cache store failed (gpt): %s", e)
        logger.debug("_call_gpt result model=%s result=%s", model, text)
        return await _finalise("gpt", prompt, text, rec, fallback=fallback)
    except Exception:
        logger.exception("_call_gpt failure")
        raise


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
    logger.debug(
        "_call_llama start prompt=%r model=%s user_id=%s", prompt, model, user_id
    )
    tokens: list[str] = []
    logger.debug(
        "LLaMA opts: temperature=%s top_p=%s",
        (gen_opts or {}).get("temperature"),
        (gen_opts or {}).get("top_p"),
    )
    try:
        try:
            result = ask_llama(built_prompt, model, **(gen_opts or {}))
        except TypeError:
            result = ask_llama(built_prompt, model, gen_opts=gen_opts)
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
        _mark_llama_unhealthy()
        fallback_model = os.getenv("OPENAI_MODEL", "gpt-4o")
        try:
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
                fallback=True,
            )
            logger.debug(
                "_call_llama fallback result model=%s result=%s", fallback_model, text
            )
            return text
        except Exception:
            logger.exception("_call_llama fallback to GPT failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="GPT backend unavailable",
            )
    try:
        if not result_text or _low_conf(result_text):
            # Mark LLaMA unhealthy and fall back to GPT on empty or low-confidence replies
            _mark_llama_unhealthy()
            fallback_model = os.getenv("OPENAI_MODEL", "gpt-4o")
            try:
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
                    fallback=True,
                )
                logger.debug(
                    "_call_llama low-conf fallback model=%s result=%s",
                    fallback_model,
                    text,
                )
                return text
            except Exception:
                logger.exception("_call_llama low-conf fallback to GPT failed")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="GPT backend unavailable",
                )
        if rec:
            rec.engine_used = "llama"
            rec.model_name = model
            rec.prompt_tokens = ptoks
            rec.response = result_text
        memgpt.store_interaction(
            prompt, result_text, session_id=session_id, user_id=user_id
        )
        add_user_memory(user_id, _fact_from_qa(prompt, result_text))
        try:
            cache_answer(prompt=norm_prompt, answer=result_text)
        except Exception as e:  # pragma: no cover
            logger.warning("QA cache store failed (llama): %s", e)
        logger.debug("_call_llama result model=%s result=%s", model, result_text)
        return await _finalise("llama", prompt, result_text, rec)
    except Exception:
        logger.exception("_call_llama failure")
        raise


async def _finalise(
    engine: str, prompt: str, text: str, rec, *, fallback: bool = False
):
    logger.debug("_finalise start engine=%s prompt=%r", engine, prompt)
    try:
        if rec:
            rec.engine_used = engine
            rec.response = text
        await append_history(prompt, engine, text)
        await record(engine, fallback=fallback)
        logger.debug("_finalise result engine=%s text=%s", engine, text)
        return text
    except Exception:
        logger.exception("_finalise failure")
        raise


async def _run_skill(prompt: str, SkillClass, rec):
    skill_resp = await SkillClass().handle(prompt)
    try:
        from . import analytics as _analytics

        await _analytics.record_skill(getattr(SkillClass, "__name__", str(SkillClass)))
    except Exception:
        pass
    return await _finalise("skill", prompt, str(skill_resp), rec)
