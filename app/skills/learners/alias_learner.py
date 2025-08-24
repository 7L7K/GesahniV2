"""
Harvest stable phrases for aliases and propose suggestions.

Heuristic: find repeated free-text mentions that map to the same entity via
alias_store or HA resolution and propose an alias if repeated >= 3 times.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ..ledger import _inmem


def find_alias_candidates(min_occurrences: int = 3) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for e in _inmem:
        md = e.get("metadata") or {}
        phrase = md.get("phrase")
        entity = md.get("entity")
        if phrase and entity:
            key = f"{phrase}|{entity}"
            counts[key] = counts.get(key, 0) + 1

    suggestions: List[Dict[str, Any]] = []
    for k, v in counts.items():
        if v >= min_occurrences:
            phrase, entity = k.split("|", 1)
            suggestions.append({"type": "alias", "proposal": f"When you say '{phrase}', map to {entity}", "why": f"seen {v} times", "candidate": {"phrase": phrase, "entity": entity}})
    return suggestions


