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
from .otel_utils import start_span, set_error
from .memory.profile_store import profile_store, CANONICAL_KEYS
try:  # optional: new retrieval pipeline
    from .retrieval.pipeline import run_pipeline as _run_retrieval_pipeline
except Exception:  # pragma: no cover
    _run_retrieval_pipeline = None  # type: ignore
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

# Environment variables for routing configuration
ROUTER_BUDGET_MS = int(os.getenv("ROUTER_BUDGET_MS", "7000"))
OPENAI_TIMEOUT_MS = int(os.getenv("OPENAI_TIMEOUT_MS", "6000"))
OLLAMA_TIMEOUT_MS = int(os.getenv("OLLAMA_TIMEOUT_MS", "4500"))

# Allow-list validation
ALLOWED_GPT_MODELS = os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4o-mini,gpt-4.1-nano").split(",")
ALLOWED_LLAMA_MODELS = os.getenv("ALLOWED_LLAMA_MODELS", "llama3,llama3.2,llama3.1").split(",")

def _validate_model_allowlist(model: str, vendor: str) -> None:
    """Validate model against allow-list before any vendor imports."""
    if vendor == "openai":
        if model not in ALLOWED_GPT_MODELS:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "model_not_allowed",
                    "model": model,
                    "vendor": vendor,
                    "allowed": ALLOWED_GPT_MODELS
                }
            )
    elif vendor == "ollama":
        if model not in ALLOWED_LLAMA_MODELS:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "model_not_allowed", 
                    "model": model,
                    "vendor": vendor,
                    "allowed": ALLOWED_LLAMA_MODELS
                }
            )
    else:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "unknown_model",
                "model": model,
                "hint": f"allowed: {', '.join(ALLOWED_GPT_MODELS + ALLOWED_LLAMA_MODELS)}"
            }
        )

def _check_vendor_health(vendor: str) -> bool:
    """Check if vendor is healthy without importing vendor modules."""
    if vendor == "openai":
        # Check OpenAI health (implement based on your OpenAI integration)
        return True  # Placeholder - implement actual health check
    elif vendor == "ollama":
        return llama_integration.LLAMA_HEALTHY and not llama_integration.llama_circuit_open
    return False

def _get_fallback_vendor(vendor: str) -> str:
    """Get the opposite vendor for fallback."""
    return "ollama" if vendor == "openai" else "openai"

def _get_fallback_model(vendor: str) -> str:
    """Get the default model for the fallback vendor."""
    if vendor == "openai":
        return "gpt-4o"  # Default GPT model
    else:
        return "llama3"  # Default LLaMA model

def _dry(engine: str, model: str) -> str:
    """Dry run function for testing."""
    label = model.split(":")[0] if engine == "llama" else model
    msg = f"[dry-run] would call {engine} {label}"
    logger.info(msg)
    return msg

def _user_circuit_open(user_id: str) -> bool:
    """Check if user-specific circuit breaker is open."""
    # Implement user-specific circuit breaker logic
    # For now, return False (circuit closed)
    return False

import json
import uuid
from datetime import datetime, timezone

def _log_golden_trace(
    request_id: str,
    user_id: str | None,
    path: str,
    shape: str,
    normalized_from: str | None,
    override_in: str | None,
    intent: str,
    tokens_est: int,
    picker_reason: str,
    chosen_vendor: str,
    chosen_model: str,
    dry_run: bool,
    cb_user_open: bool,
    cb_global_open: bool,
    allow_fallback: bool,
    stream: bool,
    tokens_est_method: str = "approx",
    keyword_hit: str | None = None,
) -> None:
    """Emit exactly one post-decision log before adapter call. Make it the law."""
    trace = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "rid": request_id,
        "uid": user_id,
        "path": path,
        "shape": shape,
        "normalized_from": normalized_from,
        "override_in": override_in,
        "intent": intent,
        "tokens_est": tokens_est,
        "tokens_est_method": tokens_est_method,
        "picker_reason": picker_reason,
        "chosen_vendor": chosen_vendor,
        "chosen_model": chosen_model,
        "dry_run": dry_run,
        "cb_user_open": cb_user_open,
        "cb_global_open": cb_global_open,
        "allow_fallback": allow_fallback,
        "stream": stream,
    }
    
    if keyword_hit:
        trace["keyword_hit"] = keyword_hit
    
    print(f"🎯 GOLDEN_TRACE: {json.dumps(trace)}")
    
    # Emit metrics
    try:
        from .metrics import ROUTER_REQUESTS_TOTAL
        ROUTER_REQUESTS_TOTAL.labels(vendor=chosen_vendor, model=chosen_model, reason=picker_reason).inc()
    except Exception:
        pass


def _log_routing_decision(
    override_in: str | None,
    intent: str,
    tokens_est: int,
    picker_reason: str,
    chosen_vendor: str,
    chosen_model: str,
    dry_run: bool,
    cb_user_open: bool,
    cb_global_open: bool,
    shape: str,
    normalized_from: str | None,
) -> None:
    """Log the final routing decision for auditability."""
    print(
        f"🎯 ROUTING DECISION: "
        f"override_in={override_in}, intent={intent}, tokens_est={tokens_est}, "
        f"picker_reason={picker_reason}, chosen_vendor={chosen_vendor}, chosen_model={chosen_model}, "
        f"dry_run={dry_run}, cb_user_open={cb_user_open}, cb_global_open={cb_global_open}, "
        f"shape={shape}, normalized_from={normalized_from}"
    )


# ---------------------------------------------------------------------------
# Constants / Config
# ---------------------------------------------------------------------------
ALLOWED_GPT_MODELS: set[str] = set(
    filter(
        None, os.getenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo").split(",")
    )
)
ALLOWED_LLAMA_MODELS: set[str] = set(
    filter(None, os.getenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3").split(","))
)
CATALOG = BUILTIN_CATALOG  # allows tests to monkey‑patch
_SMALLTALK = SmalltalkSkill()

# Mirror of llama_integration health flag so tests can adjust routing.
LLAMA_HEALTHY: bool = True

# ---------------------------------------------------------------------------
# Per-user LLaMA circuit breaker (local to router)
# ---------------------------------------------------------------------------
_USER_CB_THRESHOLD = int(os.getenv("LLAMA_USER_CB_THRESHOLD", "3"))
_USER_CB_COOLDOWN = float(os.getenv("LLAMA_USER_CB_COOLDOWN", "120"))
_llama_user_failures: dict[str, tuple[int, float]] = {}

def _user_circuit_open(user_id: str) -> bool:
    rec = _llama_user_failures.get(user_id)
    if not rec:
        return False
    count, last_ts = rec
    if count >= _USER_CB_THRESHOLD and (time := __import__("time")).time() - last_ts < _USER_CB_COOLDOWN:
        return True
    return False

def _user_cb_record_failure(user_id: str) -> None:
    t = (__import__("time").time())
    count, _ = _llama_user_failures.get(user_id, (0, 0.0))
    if t - _ >= _USER_CB_COOLDOWN:
        count = 0
    _llama_user_failures[user_id] = (count + 1, t)

def _user_cb_reset(user_id: str) -> None:
    _llama_user_failures.pop(user_id, None)

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


def _classify_profile_question(text: str) -> tuple[bool, str | None]:
    """Return (is_profile_fact, canonical_key|None).

    Simple heuristic mapper for short asks like "what's my favorite color".
    """
    p = (text or "").lower().strip()
    # map phrases to canonical keys
    mapping = {
        "favorite color": "favorite_color",
        "favourite color": "favorite_color",
        "name": "preferred_name",
        "preferred name": "preferred_name",
        "timezone": "timezone",
        "time zone": "timezone",
        "locale": "locale",
        "home city": "home_city",
        "city do i live": "home_city",
        "music service": "music_service",
        "spotify or apple": "music_service",
    }
    for phrase, key in mapping.items():
        if phrase in p:
            return True, key
    # generic patterns
    if p.startswith("what's my ") or p.startswith("what is my "):
        for key in CANONICAL_KEYS:
            if key.replace("_", " ") in p:
                return True, key
    return False, None


def _maybe_extract_confirmation(text: str) -> str | None:
    """If text cleanly states a value (e.g., "it's blue"), return the value."""
    t = (text or "").strip().strip(". ")
    lowers = t.lower()
    for prefix in ("it's ", "its ", "it is ", "is ", "= "):
        if lowers.startswith(prefix):
            return t[len(prefix):].strip()
    # "blue" as a single token confirmation
    if len(t.split()) <= 3 and len(t) <= 32:
        return t
    return None


_BASIC_COLORS: set[str] = {
    "red","blue","green","yellow","purple","orange","pink","black","white","gray","grey","brown","teal","cyan","magenta","maroon","navy","gold","silver"
}


def _maybe_update_profile_from_statement(user_id: str, text: str) -> bool:
    """Parse simple statements and upsert profile facts.

    Examples:
    - "my favorite color is blue" → favorite_color=blue
    - "it's blue" → favorite_color=blue (when value is a known color)
    - "call me Alex" / "my name is Alex" → preferred_name=Alex
    - "i live in Detroit" → home_city=Detroit
    """
    t = (text or "").strip()
    tl = t.lower()
    updated = False
    try:
        # favorite color variants
        for phrase in ("my favorite color is ", "my favourite color is ", "favorite color is ", "favourite color is "):
            if tl.startswith(phrase):
                val = t[len(phrase):].strip(" .")
                if val:
                    profile_store.upsert(user_id, "favorite_color", val, source="utterance")
                    updated = True
                    return True
        # generic color-only confirmation
        conf = _maybe_extract_confirmation(t)
        if conf and conf.lower() in _BASIC_COLORS:
            profile_store.upsert(user_id, "favorite_color", conf, source="utterance")
            return True
        # name
        for phrase in ("my name is ", "call me "):
            if tl.startswith(phrase):
                val = t[len(phrase):].strip(" .")
                if val:
                    profile_store.upsert(user_id, "preferred_name", val, source="utterance")
                    return True
        # home city
        for phrase in ("i live in ", "my home city is "):
            if tl.startswith(phrase):
                val = t[len(phrase):].strip(" .")
                if val:
                    profile_store.upsert(user_id, "home_city", val, source="utterance")
                    return True
    except Exception:
        return updated
    return updated

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
    stream_hook: Callable[[str], Awaitable[None]] | None = None,
    shape: str = "text",
    normalized_from: str | None = None,
    allow_fallback: bool = True,
    **gen_opts: Any,
) -> Any:
    # Generate unique request ID for tracing
    request_id = str(uuid.uuid4())[:8]
    
    # Step 2: Log model routing inputs and decisions
    print(f"🎯 ROUTE_PROMPT: prompt='{prompt[:50]}...', model_override={model_override}, user_id={user_id}, gen_opts={gen_opts}")
    
    logger.debug(
        "route_prompt start prompt=%r model_override=%s user_id=%s",
        prompt,
        model_override,
        user_id,
    )
    
        # Detect intent and count tokens
    norm_prompt = prompt.lower().strip()
    intent, priority = detect_intent(prompt)
    tokens = count_tokens(prompt)
    
    # Check for debug mode
    debug_route = bool(os.getenv("DEBUG_MODEL_ROUTING", "0"))
    
    # Determine initial routing decision
    if model_override:
        # Model override path
        mv = model_override.strip()
        print(f"🔀 MODEL OVERRIDE: {mv} requested - bypassing skills")
        logger.info("🔀 Model override requested → %s", mv)
        
        # Determine vendor from model name
        if mv.startswith("gpt"):
            chosen_vendor = "openai"
            chosen_model = mv
            picker_reason = "explicit_override"
        elif mv.startswith("llama"):
            chosen_vendor = "ollama"
            chosen_model = mv
            picker_reason = "explicit_override"
        else:
            # Unknown model - validate before any imports
            _validate_model_allowlist(mv, "unknown")
            # This should never be reached due to validation above
            raise HTTPException(status_code=400, detail=f"Unknown model '{mv}'")
        
        # Validate against allow-list before any vendor imports
        _validate_model_allowlist(chosen_model, chosen_vendor)
        
        # Check vendor health
        if not _check_vendor_health(chosen_vendor):
            if not allow_fallback:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "vendor_unavailable",
                        "vendor": chosen_vendor
                    }
                )
            else:
                # Fallback to opposite vendor
                fallback_vendor = _get_fallback_vendor(chosen_vendor)
                fallback_model = _get_fallback_model(fallback_vendor)
                fallback_reason = f"fallback_{fallback_vendor}"
                
                # Validate fallback model
                _validate_model_allowlist(fallback_model, fallback_vendor)
                
                # Check fallback vendor health
                if not _check_vendor_health(fallback_vendor):
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error": "all_vendors_unavailable",
                            "primary": chosen_vendor,
                            "fallback": fallback_vendor
                        }
                    )
                
                # Use fallback
                chosen_vendor = fallback_vendor
                chosen_model = fallback_model
                picker_reason = fallback_reason
                
                # Log fallback metrics
                try:
                    from .metrics import ROUTER_FALLBACKS_TOTAL
                    ROUTER_FALLBACKS_TOTAL.labels(
                        from_vendor=_get_fallback_vendor(chosen_vendor),
                        to_vendor=chosen_vendor,
                        reason="vendor_unhealthy"
                    ).inc()
                except Exception:
                    pass
    else:
        # Default picker path
        engine, model_name, picker_reason, keyword_hit = pick_model(prompt, intent, tokens)
        print(f"🎯 DEFAULT MODEL SELECTION: engine={engine}, model={model_name}, intent={intent}, reason={picker_reason}")
        
        # Determine vendor
        chosen_vendor = "openai" if engine == "gpt" else "ollama"
        chosen_model = model_name
        
        # Validate against allow-list
        _validate_model_allowlist(chosen_model, chosen_vendor)
        
        # Check vendor health
        if not _check_vendor_health(chosen_vendor):
            if not allow_fallback:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "error": "vendor_unavailable",
                        "vendor": chosen_vendor
                    }
                )
            else:
                # Fallback to opposite vendor
                fallback_vendor = _get_fallback_vendor(chosen_vendor)
                fallback_model = _get_fallback_model(fallback_vendor)
                fallback_reason = f"fallback_{fallback_vendor}"
                
                # Validate fallback model
                _validate_model_allowlist(fallback_model, fallback_vendor)
                
                # Check fallback vendor health
                if not _check_vendor_health(fallback_vendor):
                    raise HTTPException(
                        status_code=503,
                        detail={
                            "error": "all_vendors_unavailable",
                            "primary": chosen_vendor,
                            "fallback": fallback_vendor
                        }
                    )
                
                # Use fallback
                chosen_vendor = fallback_vendor
                chosen_model = fallback_model
                picker_reason = fallback_reason
                keyword_hit = None  # Reset keyword for fallback
                
                # Log fallback metrics
                try:
                    from .metrics import ROUTER_FALLBACKS_TOTAL
                    ROUTER_FALLBACKS_TOTAL.labels(
                        from_vendor=_get_fallback_vendor(chosen_vendor),
                        to_vendor=chosen_vendor,
                        reason="vendor_unhealthy"
                    ).inc()
                except Exception:
                    pass

    # Check circuit breakers
    cb_global_open = llama_circuit_open
    cb_user_open = _user_circuit_open(user_id) if user_id else False
    
    # Log the final routing decision
    _log_golden_trace(
        request_id=request_id,
        user_id=user_id,
        path="/v1/ask",
        shape=shape,
        normalized_from=normalized_from,
        override_in=model_override,
        intent=intent,
        tokens_est=tokens,
        picker_reason=picker_reason,
        chosen_vendor=chosen_vendor,
        chosen_model=chosen_model,
        dry_run=debug_route,
        cb_user_open=cb_user_open,
        cb_global_open=cb_global_open,
        allow_fallback=allow_fallback,
        stream=bool(stream_cb),
        keyword_hit=keyword_hit if 'keyword_hit' in locals() else None,
    )
    
    # Execute the chosen vendor
    if debug_route:
        result = _dry(chosen_vendor, chosen_model)
        return result
    
    if chosen_vendor == "openai":
        # Lazy import OpenAI adapter
        try:
            from .gpt_client import ask_gpt
            result = await ask_gpt(
                prompt,
                model=chosen_model,
                stream_cb=stream_cb,
                **gen_opts
            )
            return result
        except Exception as e:
            if allow_fallback and chosen_vendor != _get_fallback_vendor(chosen_vendor):
                # Try fallback
                fallback_vendor = _get_fallback_vendor(chosen_vendor)
                fallback_model = _get_fallback_model(fallback_vendor)
                
                # Log fallback metrics
                try:
                    from .metrics import ROUTER_FALLBACKS_TOTAL
                    ROUTER_FALLBACKS_TOTAL.labels(
                        from_vendor=chosen_vendor,
                        to_vendor=fallback_vendor,
                        reason="vendor_error"
                    ).inc()
                except Exception:
                    pass
                
                # Try fallback vendor
                if fallback_vendor == "ollama":
                    try:
                        from .llama_integration import ask_llama
                        result = await ask_llama(
                            prompt,
                            model=fallback_model,
                            stream_cb=stream_cb,
                            **gen_opts
                        )
                        return result
                    except Exception:
                        pass
                
                # If fallback also fails, raise original error
                raise e
            else:
                raise e
    
    elif chosen_vendor == "ollama":
        # Lazy import Ollama adapter
        try:
            from .llama_integration import ask_llama
            result = await ask_llama(
                prompt,
                model=chosen_model,
                stream_cb=stream_cb,
                **gen_opts
            )
            return result
        except Exception as e:
            if allow_fallback and chosen_vendor != _get_fallback_vendor(chosen_vendor):
                # Try fallback
                fallback_vendor = _get_fallback_vendor(chosen_vendor)
                fallback_model = _get_fallback_model(fallback_vendor)
                
                # Log fallback metrics
                try:
                    from .metrics import ROUTER_FALLBACKS_TOTAL
                    ROUTER_FALLBACKS_TOTAL.labels(
                        from_vendor=chosen_vendor,
                        to_vendor=fallback_vendor,
                        reason="vendor_error"
                    ).inc()
                except Exception:
                    pass
                
                # Try fallback vendor
                if fallback_vendor == "openai":
                    try:
                        from .gpt_client import ask_gpt
                        result = await ask_gpt(
                            prompt,
                            model=fallback_model,
                            stream_cb=stream_cb,
                            **gen_opts
                        )
                        return result
                    except Exception:
                        pass
                
                # If fallback also fails, raise original error
                raise e
            else:
                raise e
    
    # This should never be reached
    raise HTTPException(status_code=500, detail="No valid vendor found")


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
    except Exception as e:
        # Preserve provider 4xx as 4xx for transparency; otherwise propagate
        try:
            import httpx as _httpx  # type: ignore
            if isinstance(e, _httpx.HTTPStatusError):
                sc = int(getattr(getattr(e, "response", None), "status_code", 500) or 500)
                if 400 <= sc < 500:
                    msg = None
                    try:
                        data = e.response.json()
                        msg = data.get("error") or data.get("message") or data.get("detail")
                    except Exception:
                        try:
                            msg = e.response.text
                        except Exception:
                            msg = str(e)
                    from fastapi import HTTPException as _HTTPEx  # type: ignore
                    raise _HTTPEx(status_code=sc, detail=str(msg or "provider_error"))
        except Exception:
            pass
        raise
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
        memgpt.write_claim(
            session_id=session_id,
            user_id=user_id,
            claim_text=_fact_from_qa(prompt, text),
            evidence_links=[],
            claim_type="fact",
            entities=[],
            confidence=0.6,
        )
    except Exception:
        pass
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
        memgpt.write_claim(
            session_id=session_id,
            user_id=user_id,
            claim_text=_fact_from_qa(prompt, result_text),
            evidence_links=[],
            claim_type="fact",
            entities=[],
            confidence=0.6,
        )
    except Exception:
        pass
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
    print(f"🤖 CALLING GPT: model={model}, prompt_len={len(prompt)}")
    logger.debug(
        "_call_gpt start prompt=%r model=%s user_id=%s", prompt, model, user_id
    )
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
    except Exception as e:
        # Preserve provider 4xx as 4xx
        try:
            import httpx as _httpx  # type: ignore
            if isinstance(e, _httpx.HTTPStatusError):
                sc = int(getattr(getattr(e, "response", None), "status_code", 500) or 500)
                if 400 <= sc < 500:
                    msg = None
                    try:
                        data = e.response.json()
                        msg = data.get("error") or data.get("message") or data.get("detail")
                    except Exception:
                        try:
                            msg = e.response.text
                        except Exception:
                            msg = str(e)
                    from fastapi import HTTPException as _HTTPEx  # type: ignore
                    raise _HTTPEx(status_code=sc, detail=str(msg or "provider_error"))
        except Exception:
            pass
        raise
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
            memgpt.write_claim(
                session_id=session_id,
                user_id=user_id,
                claim_text=_fact_from_qa(prompt, text),
                evidence_links=[],
                claim_type="fact",
                entities=[],
                confidence=0.6,
            )
        except Exception:
            pass
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
    print(f"🤖 CALLING LLAMA: model={model}, prompt_len={len(prompt)}")
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
            # Tag fallback for response headers via telemetry record
            try:
                if rec:
                    rec.engine_used = "gpt"
                    rec.route_reason = (rec.route_reason or "") + "|fallback_from_llama"
            except Exception:
                pass
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
                try:
                    if rec:
                        rec.engine_used = "gpt"
                        rec.route_reason = (rec.route_reason or "") + "|fallback_from_llama"
                except Exception:
                    pass
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
        try:
            memgpt.write_claim(
                session_id=session_id,
                user_id=user_id,
                claim_text=_fact_from_qa(prompt, result_text),
                evidence_links=[],
                claim_type="fact",
                entities=[],
                confidence=0.6,
            )
        except Exception:
            pass
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
