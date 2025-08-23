"""Weekly rollup condensing crumbs (lean summaries)."""

from collections.abc import Iterable


def weekly_rollup(chunks: Iterable[str]) -> str:
    items = [c.strip() for c in chunks if c and c.strip()]
    if not items:
        return ""
    # naive: keep first N and last N
    head = items[:3]
    tail = items[-2:]
    return " | ".join(head + (["…"] if len(items) > 5 else []) + tail)
