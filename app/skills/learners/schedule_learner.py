from __future__ import annotations

"""
Detect recurring actions and propose schedule suggestions.

Algorithm (design + lightweight runtime):
- Scan ledger entries for identical actions (same idempotency target) over
  the past 14 days. If >= 3 occurrences with roughly consistent times
  (within ±30 minutes), emit a suggestion.

Output format: suggestion dict with {"type": "schedule", "proposal": str, "why": str, "candidate": {...}}
"""


from datetime import datetime, timedelta
from typing import Any

from ..ledger import _inmem


def find_repeating_actions(
    window_days: int = 14, min_occurrences: int = 3, tolerance_min: int = 30
) -> list[dict[str, Any]]:
    now = datetime.now()
    start = now - timedelta(days=window_days)
    # group by action+metadata['drug'|'label'|'entity'] heuristically
    buckets: dict[str, list[datetime]] = {}
    for e in _inmem:
        try:
            ts = datetime.fromisoformat(e["ts"])
        except Exception:
            continue
        if ts < start:
            continue
        key_parts = [e.get("action")]
        md = e.get("metadata") or {}
        for k in ("drug", "label", "entity"):
            if md.get(k):
                key_parts.append(str(md.get(k)))
                break
        key = "|".join(key_parts)
        buckets.setdefault(key, []).append(ts)

    suggestions: list[dict[str, Any]] = []
    for key, times in buckets.items():
        if len(times) < min_occurrences:
            continue
        # compute if times are within tolerance (mean vs each)
        avg_minutes = sum(t.hour * 60 + t.minute for t in times) / len(times)
        if all(
            abs((t.hour * 60 + t.minute) - avg_minutes) <= tolerance_min for t in times
        ):
            # propose at rounded minute
            hour = int(avg_minutes // 60)
            minute = int(avg_minutes % 60)
            proposal = f"Enable a daily reminder at {hour:02d}:{minute:02d}?"
            suggestions.append(
                {
                    "type": "schedule",
                    "proposal": proposal,
                    "why": f"{len(times)} similar events in last {window_days} days",
                    "candidate": {"key": key, "hour": hour, "minute": minute},
                }
            )

    return suggestions
