"""Deterministic model router with self-check escalation and cache keys.

This module centralizes routing decisions for text, RAG, ops, and vision.
It is designed to be hot-reloadable via a YAML rules file so thresholds can
be tweaked at runtime without code changes.
"""

from __future__ import annotations

import os
import time
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Tuple

try:  # pragma: no cover - optional
    import yaml  # type: ignore
except Exception:  # pragma: no cover - fallback parser
    yaml = None  # type: ignore

from .token_utils import count_tokens
from .metrics import ROUTER_DECISION
from .memory.vector_store import _normalized_hash as normalized_hash
from .model_config import GPT_BASELINE_MODEL, GPT_MID_MODEL, GPT_HEAVY_MODEL


# ---------------------------------------------------------------------------
# Defaults (also mirrored in router_rules.yaml)
# ---------------------------------------------------------------------------

MAX_SHORT_PROMPT_TOKENS = 240
RAG_LONG_CONTEXT_THRESHOLD = 6000
DOC_LONG_REPLY_TARGET = 900
OPS_MAX_FILES_SIMPLE = 2
SELF_CHECK_FAIL_THRESHOLD = 0.60
# Matches cost guardrail MAX_ESCALATIONS (one retry after first try)
MAX_RETRIES_PER_REQUEST = int(os.getenv("MAX_ESCALATIONS", "1"))
# Optional guardrails
REPLY_LEN_TARGET_GRANNY = int(os.getenv("REPLY_LEN_TARGET_GRANNY", "300"))
_BUDGET_REPLY_LEN_TARGET = int(os.getenv("BUDGET_REPLY_LEN_TARGET", "180"))


# ---------------------------------------------------------------------------
# Hot-reloadable rules
# ---------------------------------------------------------------------------

_RULES_MTIME: float | None = None
_RULES_PATH = Path(os.getenv("ROUTER_RULES_PATH", "router_rules.yaml"))
_LOADED_RULES: dict[str, Any] | None = None


def _load_rules() -> dict[str, Any]:
    """Load rules from YAML if present; fall back to defaults.

    The file is re-read if its mtime changes between calls.
    """

    global _RULES_MTIME, _LOADED_RULES
    try:
        st = _RULES_PATH.stat()
    except Exception:
        _RULES_MTIME = None
        if _LOADED_RULES is None:
            _LOADED_RULES = {
                "MAX_SHORT_PROMPT_TOKENS": MAX_SHORT_PROMPT_TOKENS,
                "RAG_LONG_CONTEXT_THRESHOLD": RAG_LONG_CONTEXT_THRESHOLD,
                "DOC_LONG_REPLY_TARGET": DOC_LONG_REPLY_TARGET,
                "OPS_MAX_FILES_SIMPLE": OPS_MAX_FILES_SIMPLE,
                "SELF_CHECK_FAIL_THRESHOLD": SELF_CHECK_FAIL_THRESHOLD,
                "MAX_RETRIES_PER_REQUEST": MAX_RETRIES_PER_REQUEST,
            }
        return _LOADED_RULES

    mtime = st.st_mtime
    if _LOADED_RULES is not None and _RULES_MTIME == mtime:
        return _LOADED_RULES

    # Re-read
    try:
        if yaml is None:
            raise RuntimeError("pyyaml not installed")
        data = yaml.safe_load(_RULES_PATH.read_text(encoding="utf-8")) or {}
        rules = {
            "MAX_SHORT_PROMPT_TOKENS": int(
                data.get("MAX_SHORT_PROMPT_TOKENS", MAX_SHORT_PROMPT_TOKENS)
            ),
            "RAG_LONG_CONTEXT_THRESHOLD": int(
                data.get("RAG_LONG_CONTEXT_THRESHOLD", RAG_LONG_CONTEXT_THRESHOLD)
            ),
            "DOC_LONG_REPLY_TARGET": int(
                data.get("DOC_LONG_REPLY_TARGET", DOC_LONG_REPLY_TARGET)
            ),
            "OPS_MAX_FILES_SIMPLE": int(
                data.get("OPS_MAX_FILES_SIMPLE", OPS_MAX_FILES_SIMPLE)
            ),
            "SELF_CHECK_FAIL_THRESHOLD": float(
                data.get("SELF_CHECK_FAIL_THRESHOLD", SELF_CHECK_FAIL_THRESHOLD)
            ),
            "MAX_RETRIES_PER_REQUEST": int(
                data.get("MAX_RETRIES_PER_REQUEST", MAX_RETRIES_PER_REQUEST)
            ),
        }
        _LOADED_RULES = rules
        _RULES_MTIME = mtime
        return rules
    except Exception:
        # On parse error, keep previous if any, else defaults
        if _LOADED_RULES is None:
            _LOADED_RULES = {
                "MAX_SHORT_PROMPT_TOKENS": MAX_SHORT_PROMPT_TOKENS,
                "RAG_LONG_CONTEXT_THRESHOLD": RAG_LONG_CONTEXT_THRESHOLD,
                "DOC_LONG_REPLY_TARGET": DOC_LONG_REPLY_TARGET,
                "OPS_MAX_FILES_SIMPLE": OPS_MAX_FILES_SIMPLE,
                "SELF_CHECK_FAIL_THRESHOLD": SELF_CHECK_FAIL_THRESHOLD,
                "MAX_RETRIES_PER_REQUEST": MAX_RETRIES_PER_REQUEST,
            }
        return _LOADED_RULES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class RouteDecision:
    model: str
    reason: str
    escalated: bool = False
    attempts: int = 0
    self_check: float | None = None


def compose_cache_id(model: str, prompt: str, topk_docs: Iterable[str] | None) -> str:
    """Return cache id combining {model, prompt_hash, topk_ids} as required.

    topk_docs are hashed individually using the project-normalized hash.
    """

    prompt_h = normalized_hash(prompt)
    topk = ",".join(sorted(normalized_hash(doc) for doc in (topk_docs or [])))
    # Include version tag to allow future evolution without cross-contamination
    return f"v1|{model}|{prompt_h}|{topk}"


def route_text(
    *,
    user_prompt: str,
    prompt_tokens: int | None = None,
    retrieved_docs: Iterable[str] | None = None,
    intent: str | None = None,
    ops_files_count: int | None = None,
    attachments_count: int | None = None,
    ) -> RouteDecision:
    """Deterministic text routing with budgets and long-context handling.

    Defaults to gpt-5-nano; escalates to gpt-4.1-nano for long prompt/context,
    non-trivial attachments, or complex ops. Self-check escalations happen in
    run_with_self_check.
    """

    rules = _load_rules()
    pt = prompt_tokens if prompt_tokens is not None else count_tokens(user_prompt)
    # Fallback for single-token undercount when no tokenizer available
    if pt <= 1 and len(user_prompt) > 0:
        # Treat roughly 4 chars ≈ 1 token
        approx = max(1, len(user_prompt) // 4)
        pt = max(pt, approx)

    # Attachments heuristic: if there are any images/files, prefer mid-tier snapshot
    if (attachments_count or 0) > 0:
        ROUTER_DECISION.labels("attachments").inc()
        return RouteDecision(model="gpt-4.1-nano", reason="attachments")

    # Ops heuristic: escalate if many files
    if intent == "ops" and ops_files_count is not None:
        if ops_files_count <= rules["OPS_MAX_FILES_SIMPLE"]:
            ROUTER_DECISION.labels("ops-simple").inc()
            return RouteDecision(model="gpt-5-nano", reason="ops-simple")
        ROUTER_DECISION.labels("ops-complex").inc()
        return RouteDecision(model="gpt-4.1-nano", reason="ops-complex")

    # Long prompt (token-based)
    if pt > rules["MAX_SHORT_PROMPT_TOKENS"]:
        ROUTER_DECISION.labels("long-prompt").inc()
        return RouteDecision(model="gpt-4.1-nano", reason="long-prompt")
    # Fallback: char-length heuristic when tokenizer underestimates
    char_len = len(user_prompt or "")
    if char_len > (rules["MAX_SHORT_PROMPT_TOKENS"] * 3):
        ROUTER_DECISION.labels("long-prompt").inc()
        return RouteDecision(model="gpt-4.1-nano", reason="long-prompt")

    # Long RAG context (estimate by tokens in docs)
    if retrieved_docs:
        rag_tokens = sum(count_tokens(d) for d in retrieved_docs)
        # Adjust for naive fallback that undercounts (no whitespace)
        approx_tokens = sum(max(1, len(d) // 4) for d in retrieved_docs)
        rag_tokens = max(rag_tokens, approx_tokens)
        if rag_tokens > rules["RAG_LONG_CONTEXT_THRESHOLD"]:
            ROUTER_DECISION.labels("long-context").inc()
            return RouteDecision(model="gpt-4.1-nano", reason="long-context")
        # Fallback: char-length heuristic for doc context when tokenizer underestimates
        char_total = sum(len(d) for d in retrieved_docs)
        # Treat >5k chars of external context as long in fallback mode
        if char_total > 5000:
            ROUTER_DECISION.labels("long-context").inc()
            return RouteDecision(model="gpt-4.1-nano", reason="long-context")

    ROUTER_DECISION.labels("default").inc()
    return RouteDecision(model="gpt-5-nano", reason="default")


def _heuristic_self_check(
    user_prompt: str,
    answer: str,
    retrieved_docs: Iterable[str] | None = None,
    *,
    model: str | None = None,
    system_prompt: str | None = None,
) -> float:
    """Pure-Python heuristic self-check in [0,1].

    This provides deterministic scoring in tests without network calls.
    """

    if not answer or not answer.strip():
        return 0.0
    text = answer.strip().lower()
    if any(x in text for x in ("i don't know", "not sure", "cannot help")):
        return 0.2
    # Completeness proxy: aim for at least a model/mode-dependent target.
    rules = _load_rules()
    min_len = 60
    # Default long target for document-like tasks
    target = rules["DOC_LONG_REPLY_TARGET"]
    # Budget guardrail: when quota is breached, reduce target aggressively
    if os.getenv("BUDGET_QUOTA_BREACHED", "0").lower() in {"1", "true", "yes"}:
        target = max(min_len, _BUDGET_REPLY_LEN_TARGET)
    # Granny mode prefers shorter replies on baseline model
    sp = (system_prompt or "").lower()
    if "granny mode" in sp and (model or "").startswith("gpt-5-nano"):
        target = max(min_len, REPLY_LEN_TARGET_GRANNY)
    length_norm = min(1.0, max(min_len, len(answer)) / max(min_len, float(target)))
    # Factuality proxy: overlap with retrieved docs if provided
    factual = 0.7
    if retrieved_docs:
        src = " ".join(retrieved_docs).lower()
        overlap = 0.0
        for token in set(text.split()):
            if token.isalpha() and token in src:
                overlap += 1
        factual = min(1.0, 0.4 + overlap / 50.0)
    # Reasoning proxy: presence of because/therefore/so suggests structure
    reasoning = 0.6 + (0.2 if any(k in text for k in ("because", "therefore", "so")) else 0)
    score = max(0.0, min(1.0, 0.25 * length_norm + 0.45 * factual + 0.30 * reasoning))
    return float(score)


async def run_with_self_check(
    *,
    ask_func,
    model: str,
    user_prompt: str,
    system_prompt: str | None,
    retrieved_docs: Iterable[str] | None,
    threshold: float | None = None,
    max_retries: int | None = None,
    on_token=None,
    stream: bool = False,
    allow_test: bool = False,
) -> Tuple[str, str, str, float, int, int, float, bool]:
    """Execute a model call with self-check escalation logic.

    Returns: (text, final_model, reason, self_check, prompt_tokens, completion_tokens, cost, escalated)
    """

    rules = _load_rules()
    thresh = float(rules["SELF_CHECK_FAIL_THRESHOLD"] if threshold is None else threshold)
    effective_max = int(rules["MAX_RETRIES_PER_REQUEST"] if max_retries is None else max_retries)
    retries_left = int(effective_max)
    # If budget/quota is breached, disable escalations entirely
    if os.getenv("BUDGET_QUOTA_BREACHED", "0").lower() in {"1", "true", "yes"}:
        retries_left = 0

    current_model = model
    reason = "initial"
    escalated = False

    # Wrapper around ask_func to standardize return
    async def _call(m: str) -> Tuple[str, int, int, float]:
        # ask_func must be compatible with gpt_client.ask_gpt signature
        # Be tolerant of older stubs that don't accept streaming kwargs.
        try:
            text, pt, ct, cost = await ask_func(
                user_prompt,
                m,
                system_prompt,
                stream=stream,
                on_token=on_token,
                allow_test=allow_test,
            )
        except TypeError:
            text, pt, ct, cost = await ask_func(
                user_prompt,
                m,
                system_prompt,
            )
        return text, pt, ct, cost

    # attempt 1
    text, pt, ct, cost = await _call(current_model)
    score = _heuristic_self_check(
        user_prompt,
        text,
        retrieved_docs,
        model=current_model,
        system_prompt=system_prompt,
    )
    if score >= thresh:
        return text, current_model, reason, score, pt, ct, cost, escalated

    # escalate chain
    while retries_left > 0:
        retries_left -= 1
        # With a single allowed retry, prefer mid-tier unless threshold demands final
        if int(effective_max) <= 1:
            if thresh >= 0.8:
                current_model = GPT_HEAVY_MODEL
                reason = "self-check-final"
            else:
                current_model = "gpt-4.1-nano"
                reason = "self-check-escalation"
            escalated = True
        else:
            # first escalation → gpt-4.1-nano if not already
            if current_model != "gpt-4.1-nano":
                current_model = "gpt-4.1-nano"
                reason = "self-check-escalation"
                escalated = True
            else:
                # final retry → heavy model
                current_model = GPT_HEAVY_MODEL
                reason = "self-check-final"
                escalated = True
        text, pt, ct, cost = await _call(current_model)
        score = _heuristic_self_check(
            user_prompt,
            text,
            retrieved_docs,
            model=current_model,
            system_prompt=system_prompt,
        )
        if score >= thresh:
            break

    return text, current_model, reason, score, pt, ct, cost, escalated


# ---------------------------------------------------------------------------
# Vision routing
# ---------------------------------------------------------------------------


def triage_scene_risk(text_hint: str | None) -> str:
    """Return simple risk category for a scene from an optional text hint."""

    if not text_hint:
        return "low"
    t = text_hint.lower()
    if any(k in t for k in ("injury", "accident", "fire", "weapon", "blood", "unsafe")):
        return "high"
    if any(k in t for k in ("warning", "caution", "risk", "damaged")):
        return "medium"
    return "low"


_VISION_DAY: str | None = None
_VISION_COUNT: int = 0
_VISION_LAST_MAX: int | None = None


def _vision_daily_cap(max_per_day: int) -> bool:
    """Return True if another remote vision call is allowed today.

    Resets the simple counter when the day changes.
    """
    global _VISION_DAY, _VISION_COUNT, _VISION_LAST_MAX
    today = time.strftime("%Y-%m-%d")
    if _VISION_DAY != today:
        _VISION_DAY = today
        _VISION_COUNT = 0
        _VISION_LAST_MAX = None
    # If the configured cap changes between calls (e.g., tests), reset counter
    if _VISION_LAST_MAX is None or _VISION_LAST_MAX != max_per_day:
        _VISION_LAST_MAX = max_per_day
        _VISION_COUNT = 0
    if _VISION_COUNT >= max_per_day:
        return False
    _VISION_COUNT += 1
    return True


async def route_vision(
    *,
    ask_func,
    images: List[Any],
    text_hint: str | None = None,
    allow_test: bool = False,
) -> Tuple[str, str]:
    """Vision pipeline: local triage → gpt-4o-mini → optional gpt-4o safety retry.

    Returns (model_used, reason).
    """

    # local triage + per-day cap; treat any provided image or hint as an event
    risk = triage_scene_risk(text_hint)
    max_per_day = int(os.getenv("VISION_MAX_IMAGES_PER_DAY", "40"))
    if not _vision_daily_cap(max_per_day):
        return "local", "vision-local-cap"

    event = bool(images or text_hint)
    if not event:
        return "local", "vision-no-event"

    # snapshot with mini
    model = GPT_BASELINE_MODEL
    reason = f"vision-{risk}"
    # We do not actually call a vision API in tests; caller provides ask_func stub
    _ = await ask_func("<vision prompt>", model, None, allow_test=allow_test)

    # optional safety retry
    if risk == "high":
        model = GPT_MID_MODEL
        reason = "vision-safety"
        _ = await ask_func("<vision prompt>", model, None, allow_test=allow_test)
    return model, reason


# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------


def load_system_prompt(mode: str | None) -> Optional[str]:
    """Return system prompt text for Granny Mode or Computer Mode.

    Falls back to None when mode is unrecognized.
    """

    mode_l = (mode or "").strip().lower()
    base = Path(__file__).parent / "prompts"
    if mode_l == "granny":
        path = base / "granny_mode.txt"
    elif mode_l == "computer":
        path = base / "computer_mode.txt"
    else:
        # Load default system persona if mode unspecified
        try:
            default_path = base / "system_default.txt"
            return default_path.read_text(encoding="utf-8")
        except Exception:
            return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return None


__all__ = [
    "RouteDecision",
    "compose_cache_id",
    "route_text",
    "run_with_self_check",
    "triage_scene_risk",
    "route_vision",
    "load_system_prompt",
]





__all__ = [
    "RouteDecision",
    "compose_cache_id",
    "route_text",
    "run_with_self_check",
    "triage_scene_risk",
    "route_vision",
    "load_system_prompt",
]


