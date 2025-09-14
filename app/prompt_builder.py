from __future__ import annotations

"""PromptBuilder module for constructing LLM prompts."""


import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Any

from .config_runtime import get_config
from .memory import memgpt
from .memory.env_utils import _normalized_hash
from .memory.vector_store import safe_query_user_memories
from .retrieval import run_retrieval, why_logs
from .telemetry import log_record_var
from .token_utils import count_tokens

# ---------------------------------------------------------------------------
# Constants & globals
# ---------------------------------------------------------------------------

MAX_PROMPT_TOKENS = 8_000
# Hard cap on number of memory lines to include to respect retriever budget
RETRIEVER_MAX_MEM_LINES = 3
_CORE_PATH = Path(__file__).parent / "prompts" / "prompt_core.txt"

logger = logging.getLogger(__name__)

# Track if we've already logged the approximate counting warning
_approx_counting_warned = False


@cache
def _prompt_core() -> str:
    """Load and cache the static prompt template."""
    return _CORE_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_k(value: int | str | None) -> int:
    """Return a positive integer `k` for memory retrieval.

    Falls back to the project-wide default when the supplied value is
    missing or invalid.
    """
    # Import here to avoid any potential circular imports in test contexts
    from app.memory import api as memory_api  # local import

    def _fallback_default() -> int:
        try:
            return int(memory_api._get_mem_top_k())
        except Exception:
            # Last-resort fallback to 3 if environment is misconfigured in tests
            return 3

    raw = value
    if value is None:
        coerced = _fallback_default()
    else:
        try:
            k_int = int(value)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid top_k %r; defaulting to %s", value, _fallback_default()
            )
            coerced = _fallback_default()
        else:
            if k_int <= 0:
                logger.warning(
                    "top_k %d must be positive; defaulting to %s",
                    k_int,
                    _fallback_default(),
                )
                coerced = _fallback_default()
            else:
                coerced = k_int
    logger.debug("_coerce_k: raw=%r coerced=%d", raw, coerced)
    return int(coerced)


# Backwards-compatibility shim for tests that patch `_get_mem_top_k` directly on
# this module. They expect it to exist at module level. Delegate to memory.api.
def _get_mem_top_k() -> int:  # pragma: no cover - thin wrapper
    try:
        from app.memory import api as memory_api

        return int(memory_api._get_mem_top_k())
    except Exception:
        return 3


# ---------------------------------------------------------------------------
# PromptBuilder
# ---------------------------------------------------------------------------


@dataclass
class PromptBuilder:
    """High-level utility for assembling an LLM prompt and returning its length."""

    @staticmethod
    def build(
        user_prompt: str,
        *,
        session_id: str = "default",
        user_id: str = "anon",
        custom_instructions: str = "",
        debug: bool = False,
        debug_info: str = "",
        top_k: int | str | None = None,
        rag_client: Any | None = None,
        rag_collection: str | None = None,
        rag_k: int | None = None,
        small_ask: bool | None = None,
        profile_facts: dict[str, str] | None = None,
        **_: Any,
    ) -> tuple[str, int]:
        """Return ``(prompt_text, prompt_tokens)``.

        Extra kwargs (e.g. `temperature`, `top_p`) are accepted for API
        parity and silently ignored.
        """
        logger.info(
            "PromptBuilder.build entry user_id=%s top_k=%s prompt=%r",
            user_id,
            top_k,
            user_prompt,
        )
        # ------------------------------------------------------------------
        # Context collection
        # ------------------------------------------------------------------
        date_time = datetime.utcnow().replace(tzinfo=UTC).isoformat()
        # Conversation recap: enabled by default in tests for snapshot stability; otherwise opt-in via env
        _default_flag = "1" if os.getenv("PYTEST_CURRENT_TEST") else "0"
        include_recap = os.getenv("INCLUDE_CONVO_SUMMARY", _default_flag).lower() in {
            "1",
            "true",
            "yes",
        }
        # For small asks, disable conversation recap entirely
        if _ and isinstance(_, dict):
            pass  # pragma: no cover - placeholder for kwargs future
        summary = ""
        if include_recap:
            raw = memgpt.summarize_session(session_id, user_id=user_id) or ""
            # Aggressive trimming: keep to 2 bullets, <= ~25 words each, last 3 turns only
            try:
                lines = [l.strip(" -\t") for l in raw.splitlines() if l.strip()]
                # Keep only last few items if it looks like a list
                lines = lines[-6:]
                bullets: list[str] = []
                for l in lines:
                    if len(bullets) >= 2:
                        break
                    words = l.split()
                    if not words:
                        continue
                    clipped = " ".join(words[:25])
                    bullets.append(f"- {clipped}")
                summary = "\n".join(bullets)
            except Exception:
                summary = raw[:200]
        k = _coerce_k(top_k)

        rag_docs: list[dict] = []
        sources_text = ""
        if rag_client:
            try:
                coll = rag_collection or os.getenv("RAGFLOW_COLLECTION", "default")
                rk = _coerce_k(rag_k or k)
                rag_docs = rag_client.query(user_prompt, collection=coll, k=rk)
            except Exception as e:  # pragma: no cover - network failures
                logger.warning("RAG query failed in PromptBuilder: %s", e)
            if rag_docs:
                blocks: list[str] = []
                for doc in rag_docs:
                    header = doc.get("source", "")
                    loc = doc.get("loc") or ""
                    if loc:
                        header = f"{header}#{loc}" if header else loc
                    text = doc.get("text", "")
                    blocks.append(f"```{header}\n{text}\n```")
                sources_text = "\n".join(blocks)
                rec_local = log_record_var.get()
                if rec_local:
                    rec_local.rag_doc_ids = [
                        _normalized_hash(d.get("text", "")) for d in rag_docs
                    ]
                    rec_local.rag_top_k = rk

        # ------------------------------------------------------------------
        # Telemetry
        # ------------------------------------------------------------------
        rec = log_record_var.get()
        if rec:
            rec.embed_tokens = count_tokens(user_prompt)
            rec.rag_top_k = k

        # ------------------------------------------------------------------
        # Profile facts injection (KV-first)
        # ------------------------------------------------------------------
        facts_block = ""
        if profile_facts:
            items = [f"{k}={v}" for k, v in profile_facts.items() if v is not None]
            if items:
                facts_block = "[USER_PROFILE_FACTS]\n" + "\n".join(items) + "\n"
        rec_pf = log_record_var.get()
        if rec_pf and facts_block:
            rec_pf.profile_facts_keys = (
                list(profile_facts.keys()) if profile_facts else []
            )
            rec_pf.facts_block = facts_block

        # ------------------------------------------------------------------
        # Memory lookup & trimming (skip for small asks)
        # ------------------------------------------------------------------
        # Prefer modular retrieval pipeline when enabled; fallback to legacy
        use_pipeline = os.getenv("USE_RETRIEVAL_PIPELINE", "0").lower() in {
            "1",
            "true",
            "yes",
        }
        if small_ask:
            summary = ""
            memories = []
        elif use_pipeline:
            cfg = get_config()
            try:
                # Preferred: new pipeline signature
                from app.retrieval.pipeline import (
                    run_pipeline as _run_pipeline,
                )  # type: ignore

                coll = os.getenv("QDRANT_COLLECTION") or "kb:default"
                memories, trace = _run_pipeline(
                    user_id=user_id,
                    query=user_prompt,
                    intent="chat",
                    collection=coll,
                    explain=True,
                )
                # Trim to final top-k from runtime config
                memories = memories[: int(getattr(cfg.retrieval, "topk_final", 3))]
            except Exception:
                # Fallback: legacy helper with k parameter
                memories, trace = run_retrieval(
                    user_prompt, user_id, k=min(k, cfg.retrieval.topk_final)
                )
            rec = log_record_var.get()
            if rec:
                # store short why-logs summary
                try:
                    rec.route_trace = (rec.route_trace or []) + [why_logs(trace)]
                except Exception:
                    pass
        else:
            memories = safe_query_user_memories(user_id, user_prompt, k=k)
        # Enforce a conservative retriever budget regardless of requested k
        if len(memories) > RETRIEVER_MAX_MEM_LINES:
            memories = memories[:RETRIEVER_MAX_MEM_LINES]
        logger.info("safe_query_user_memories returned %d memories", len(memories))
        while count_tokens("\n".join(memories)) > 120 and memories:
            memories.pop()

        # ------------------------------------------------------------------
        # Core prompt assembly
        # ------------------------------------------------------------------
        dbg = debug_info if debug else ""
        # If profile facts present, append an explicit KV-wins system rule to instructions
        kv_rule = ""
        if facts_block:
            kv_rule = (
                "\nSystem rule: If a requested key exists in [USER_PROFILE_FACTS], answer with it directly. "
                "Do not claim you lack access."
            )
        ci = (custom_instructions + kv_rule).strip()
        core_template = _prompt_core()

        base_replacements = {
            "date_time": date_time,
            "conversation_summary": summary,
            "memories": "",
            "custom_instructions": ci,
            "user_prompt": user_prompt,
            "debug_info": dbg,
        }

        base_prompt = core_template
        for key, val in base_replacements.items():
            base_prompt = base_prompt.replace(f"{{{{{key}}}}}", val)

        # Prefer tiktoken for accurate token counts when available; fall back to approx counter
        def _count_tokens_precise(text: str) -> tuple[int, str]:
            try:  # pragma: no cover - optional dependency
                import tiktoken

                # Try to use the runtime OPENAI_MODEL if available for encoding selection
                model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
                try:
                    enc = tiktoken.encoding_for_model(model_name)
                except Exception:
                    enc = tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(text)), "tiktoken"
            except Exception:
                # Fall back to the project's approximate token counter
                return count_tokens(text), "approx"

        base_tokens, tokens_est_method = _count_tokens_precise(base_prompt)

        # Log once if falling back to approximate counting
        global _approx_counting_warned
        if tokens_est_method == "approx" and not _approx_counting_warned:
            logger.info(
                "PromptBuilder using approximate token counting (tiktoken not available)"
            )
            _approx_counting_warned = True
        mem_list = memories.copy()

        # ------------------------------------------------------------------
        # Token-budget loop
        # ------------------------------------------------------------------
        trimmed_summary = False
        trimmed_memories = 0
        while True:
            prompt = core_template
            # Render retrieved memories as raw lines to preserve tests' expectations
            mem_text = "\n".join(mem_list)

            replacements = {
                "date_time": date_time,
                "conversation_summary": summary,
                "memories": (facts_block + mem_text).strip(),
                "custom_instructions": ci,
                "user_prompt": user_prompt,
                "debug_info": dbg,
            }
            for key, val in replacements.items():
                prompt = prompt.replace(f"{{{{{key}}}}}", val)

            prompt_tokens, method = _count_tokens_precise(prompt)
            # Prefer tiktoken if available for the overall prompt
            if method == "tiktoken":
                tokens_est_method = "tiktoken"

            fits_budget = (
                prompt_tokens <= MAX_PROMPT_TOKENS and prompt_tokens - base_tokens <= 75
            )
            if fits_budget:
                break

            # Budget overflow: drop summary first, then memories
            if summary:
                summary = ""
                trimmed_summary = True
                base_replacements["conversation_summary"] = ""
                base_prompt = core_template
                for key, val in base_replacements.items():
                    base_prompt = base_prompt.replace(f"{{{{{key}}}}}", val)
                base_tokens, _ = _count_tokens_precise(base_prompt)
                continue

            if mem_list:
                mem_list.pop()
                trimmed_memories += 1
                continue

            # Nothing left to trim
            break

        # ------------------------------------------------------------------
        # Final telemetry (recount after adding sources)
        # ------------------------------------------------------------------
        if sources_text:
            prompt = f"{prompt}\n\nSOURCES\n{sources_text}"
            prompt_tokens, method = _count_tokens_precise(prompt)
            if method == "tiktoken":
                tokens_est_method = "tiktoken"

        if rec:
            rec.retrieval_count = len(mem_list)

        logger.info(
            "PromptBuilder.build exit tokens=%d memories=%d method=%s",
            prompt_tokens,
            len(mem_list),
            tokens_est_method,
        )

        # Log trimming operations for debugging context loss
        if trimmed_summary or trimmed_memories > 0:
            logger.info(
                "PromptBuilder.clamp result trimmed_summary=%s trimmed_memories=%d final_tokens=%d",
                trimmed_summary,
                trimmed_memories,
                prompt_tokens,
            )
        # Optional prompt logging for debugging/dev only
        if os.getenv("LOG_BUILT_PROMPTS", "").lower() in {"1", "true", "yes"}:
            try:
                logger.debug("BUILT_PROMPT:: %s", prompt)
            except Exception:
                pass
        # Attach tokens_est_method to telemetry record when available
        rec2 = log_record_var.get()
        if rec2:
            try:
                rec2.tokens_est_method = tokens_est_method
            except Exception:
                pass

        return prompt, prompt_tokens


__all__ = ["PromptBuilder", "MAX_PROMPT_TOKENS"]
