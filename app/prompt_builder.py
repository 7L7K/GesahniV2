"""PromptBuilder module for constructing LLM prompts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cache
from pathlib import Path
from typing import Any, List

from .token_utils import count_tokens
from .memory import memgpt
from .memory.env_utils import _get_mem_top_k
from .memory.vector_store import query_user_memories
from .telemetry import log_record_var

# ---------------------------------------------------------------------------
# Constants & globals
# ---------------------------------------------------------------------------

MAX_PROMPT_TOKENS = 8_000
_CORE_PATH = Path(__file__).parent / "prompts" / "prompt_core.txt"

logger = logging.getLogger(__name__)


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
    if value is None:
        return _get_mem_top_k()

    try:
        k = int(value)
    except (TypeError, ValueError):
        logger.warning("Invalid top_k %r; defaulting to %s", value, _get_mem_top_k())
        return _get_mem_top_k()

    if k <= 0:
        logger.warning("top_k %d must be positive; defaulting to %s", k, _get_mem_top_k())
        return _get_mem_top_k()

    return k


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
        **_: Any,
    ) -> tuple[str, int]:
        """Return `(prompt_text, prompt_tokens)`.

        Extra kwargs (e.g. `temperature`, `top_p`) are accepted for API
        parity and silently ignored.
        """
        # ------------------------------------------------------------------
        # Context collection
        # ------------------------------------------------------------------
        date_time = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        summary = memgpt.summarize_session(session_id, user_id=user_id) or ""
        k = _coerce_k(top_k)

        # ------------------------------------------------------------------
        # Telemetry
        # ------------------------------------------------------------------
        rec = log_record_var.get()
        if rec:
            rec.embed_tokens = count_tokens(user_prompt)
            rec.rag_top_k = k

        # ------------------------------------------------------------------
        # Memory lookup & trimming
        # ------------------------------------------------------------------
        memories: List[str] = query_user_memories(user_id, user_prompt, k=k)
        while count_tokens("\n".join(memories)) > 55 and memories:
            memories.pop()

        # ------------------------------------------------------------------
        # Core prompt assembly
        # ------------------------------------------------------------------
        dbg = debug_info if debug else ""
        core_template = _prompt_core()
        base_replacements = {
            "date_time": date_time,
            "conversation_summary": summary,
            "memories": "",
            "custom_instructions": custom_instructions,
            "user_prompt": user_prompt,
            "debug_info": dbg,
        }

        base_prompt = core_template
        for key, val in base_replacements.items():
            base_prompt = base_prompt.replace(f"{{{{{key}}}}}", val)

        base_tokens = count_tokens(base_prompt)
        mem_list = memories.copy()

        # ------------------------------------------------------------------
        # Token-budget loop
        # ------------------------------------------------------------------
        while True:
            prompt = core_template
            mem_text = "\n".join(mem_list)

            replacements = {
                "date_time": date_time,
                "conversation_summary": summary,
                "memories": mem_text,
                "custom_instructions": custom_instructions,
                "user_prompt": user_prompt,
                "debug_info": dbg,
            }
            for key, val in replacements.items():
                prompt = prompt.replace(f"{{{{{key}}}}}", val)

            prompt_tokens = count_tokens(prompt)

            fits_budget = (
                prompt_tokens <= MAX_PROMPT_TOKENS
                and prompt_tokens - base_tokens <= 75
            )
            if fits_budget:
                break

            # Budget overflow: drop summary first, then memories
            if summary:
                summary = ""
                base_replacements["conversation_summary"] = ""
                base_prompt = core_template
                for key, val in base_replacements.items():
                    base_prompt = base_prompt.replace(f"{{{{{key}}}}}", val)
                base_tokens = count_tokens(base_prompt)
                continue

            if mem_list:
                mem_list.pop()
                continue

            # Nothing left to trim
            break

        # ------------------------------------------------------------------
        # Final telemetry
        # ------------------------------------------------------------------
        if rec:
            rec.retrieval_count = len(mem_list)

        return prompt, prompt_tokens


__all__ = ["PromptBuilder", "MAX_PROMPT_TOKENS"]
