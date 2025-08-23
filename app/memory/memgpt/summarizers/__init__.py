from __future__ import annotations

from typing import Dict, List


def event_to_fact(prompt: str, answer: str) -> str:
    text = (answer or "").strip().replace("\n", " ")
    if len(text) > 160:
        text = text[:157] + "..."
    return text


def nightly_rollup(interactions: list[dict[str, str]]) -> list[str]:
    facts: list[str] = []
    for item in interactions:
        p = item.get("prompt", "")
        a = item.get("answer", "")
        facts.append(event_to_fact(p, a))
    return facts


__all__ = ["event_to_fact", "nightly_rollup"]


