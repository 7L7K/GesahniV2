from __future__ import annotations

from typing import Any, Dict, List


def why_logs(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Summarize the new pipeline trace list into a compact dict
    counts = {ev.get("event"): ev.get("meta", {}) for ev in events}
    pre = counts.get("hybrid", {}).get("dense", 0) + counts.get("hybrid", {}).get("sparse", 0)
    top = counts.get("policy_trim", {}).get("kept", 0)
    return {
        "summary": f"retrieval pre={pre} final={top}",
        "stages": counts,
    }


__all__ = ["why_logs"]


