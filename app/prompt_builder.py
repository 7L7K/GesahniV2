"""PromptBuilder module for constructing LLM prompts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Tuple

import logging

from .token_utils import count_tokens
from .memory import memgpt
from .memory.env_utils import _get_mem_top_k
from .memory.vector_store import query_user_memories
from .telemetry import log_record_var

MAX_PROMPT_TOKENS = 8_000

# Load static prompt core at import time
_CORE_PATH = Path(__file__).parent / "prompts" / "prompt_core.txt"
_PROMPT_CORE = _CORE_PATH.read_text(encoding="utf-8")
# note: if tiktoken is missing, token_utils.count_tokens will perform a
# naive word-based count which is sufficient for tests.


logger = logging.getLogger(__name__)


def _coerce_k(val: int | str | None, default: int = 5) -> int:
    """Return a positive integer for ``val`` or ``default`` when invalid."""
    try:
        k = int(val) if val is not None else default
    except (TypeError, ValueError):
        return default
    return k if k > 0 else default


@dataclass
class PromptBuilder:
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
    ) -> Tuple[str, int]:
        """Return a tuple of (prompt_str, prompt_tokens).

        Additional keyword arguments (e.g., ``temperature`` or ``top_p``)
        are accepted for compatibility with generation options and are
        currently ignored by the builder.
        """
        date_time = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        summary = memgpt.summarize_session(session_id, user_id=user_id) or ""
        if top_k is None:
            top_k = _coerce_k(_get_mem_top_k())
            logger.warning("top_k missing; defaulting to %s", top_k)
        else:
            top_k = _coerce_k(top_k)
        rec = log_record_var.get()
        if rec:
            rec.embed_tokens = count_tokens(user_prompt)
            rec.rag_top_k = top_k
        memories: List[str] = query_user_memories(user_id, user_prompt, k=top_k)[:3]
        while count_tokens("\n".join(memories)) > 55 and memories:
            memories.pop()
        dbg = debug_info if debug else ""
        base_prompt = _PROMPT_CORE
        base_replacements = {
            "date_time": date_time,
            "conversation_summary": summary,
            "memories": "",
            "custom_instructions": custom_instructions,
            "user_prompt": user_prompt,
            "debug_info": dbg,
        }
        for key, val in base_replacements.items():
            base_prompt = base_prompt.replace(f"{{{{{key}}}}}", val)
        base_tokens = count_tokens(base_prompt)

        # Token budgeting: remove summary first, then drop low-sim/oldest
        mem_list = list(memories)
        while True:
            prompt = _PROMPT_CORE
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
            if prompt_tokens <= MAX_PROMPT_TOKENS and prompt_tokens - base_tokens <= 75:
                break
            if summary:
                summary = ""
                base_replacements["conversation_summary"] = ""
                base_prompt = _PROMPT_CORE
                for key, val in base_replacements.items():
                    base_prompt = base_prompt.replace(f"{{{{{key}}}}}", val)
                base_tokens = count_tokens(base_prompt)
                continue
            if mem_list:
                mem_list.pop()
                continue
            break
        if rec:
            rec.retrieval_count = len(mem_list)
        return prompt, prompt_tokens


__all__ = ["PromptBuilder", "MAX_PROMPT_TOKENS"]
