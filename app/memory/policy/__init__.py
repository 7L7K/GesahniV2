"""Granny-tuned memory policies.

Write rules: conversational facts only. Injection rules: small and relevant.
"""

from dataclasses import dataclass


@dataclass
class MemoryPolicy:
    allow_personal_facts: bool = True
    allow_sensitive_data: bool = False
    max_snippet_length: int = 280


DEFAULT_POLICY = MemoryPolicy()


def can_write(text: str, policy: MemoryPolicy = DEFAULT_POLICY) -> bool:
    if not policy.allow_sensitive_data and any(
        k in text.lower() for k in ("ssn", "password", "bank")
    ):
        return False
    return len(text.strip()) > 0 and len(text) <= policy.max_snippet_length


def prune_injection(candidates: list[str], max_items: int = 5) -> list[str]:
    out = [c for c in candidates if len(c) <= DEFAULT_POLICY.max_snippet_length]
    return out[:max_items]
