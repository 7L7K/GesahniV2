"""Per-user budget guardrails: track usage and apply soft caps.

- Tracks daily prompt+completion tokens and rough minutes.
- When 80% of quota reached, lowers reply_len_target and disables escalations.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Dict


_STATE: Dict[str, Dict[str, float]] = {}
_DAY_EPOCH: float | None = None


def _today_epoch() -> float:
    return time.time() // 86400


def _reset_if_new_day() -> None:
    global _DAY_EPOCH, _STATE
    now = _today_epoch()
    if _DAY_EPOCH is None or _DAY_EPOCH != now:
        _DAY_EPOCH = now
        _STATE.clear()


def _quotas() -> tuple[int, float]:
    max_tokens = int(os.getenv("DAILY_TOKEN_CAP", "200000"))  # ~200k tokens
    max_minutes = float(os.getenv("DAILY_MINUTES_CAP", "60"))
    return max_tokens, max_minutes


def add_usage(user_id: str, *, prompt_tokens: int = 0, completion_tokens: int = 0, minutes: float = 0.0) -> None:
    _reset_if_new_day()
    state = _STATE.setdefault(user_id, {"tokens": 0.0, "minutes": 0.0})
    state["tokens"] += float(prompt_tokens + completion_tokens)
    state["minutes"] += float(minutes)


def get_budget_state(user_id: str) -> Dict[str, object]:
    _reset_if_new_day()
    max_tokens, max_minutes = _quotas()
    st = _STATE.get(user_id, {"tokens": 0.0, "minutes": 0.0})
    frac_tokens = (st["tokens"] / max_tokens) if max_tokens > 0 else 0.0
    frac_minutes = (st["minutes"] / max_minutes) if max_minutes > 0 else 0.0
    frac = max(frac_tokens, frac_minutes)
    threshold = float(os.getenv("BUDGET_SOFT_THRESHOLD", "0.8"))
    breached = frac >= threshold
    # Allow global override for tests
    if os.getenv("BUDGET_QUOTA_BREACHED", "").lower() in {"1", "true", "yes"}:
        breached = True
    reply_len_target = "short" if breached else "normal"
    escalate_allowed = not breached
    return {
        "tokens_used": st["tokens"],
        "minutes_used": st["minutes"],
        "reply_len_target": reply_len_target,
        "escalate_allowed": escalate_allowed,
    }


__all__ = ["add_usage", "get_budget_state"]


