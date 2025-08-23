from __future__ import annotations

import re
from typing import Any

from ..decisions import get_explain as _get
from ..decisions import get_recent as _recent
from .base import Skill


class ExplainRouteSkill(Skill):
    PATTERNS = [
        re.compile(r"why\s+llama\??", re.I),
        re.compile(r"explain\s+route(?:\s+([a-f0-9\-]{8,}))?", re.I),
        re.compile(r"/explain(?:\?req_id=(?P<rid>[a-f0-9\-]{8,}))?", re.I),
    ]

    def _format(self, data: dict[str, Any] | None) -> str:
        if not data:
            return "No routing record found."
        parts: list[str] = []
        parts.append(
            f"engine={data.get('engine')} model={data.get('model')} reason={data.get('route_reason')}"
        )
        if data.get("latency_ms") is not None:
            parts.append(f"latency={int(data['latency_ms'])}ms")
        if data.get("cache_hit"):
            sim = data.get("cache_similarity")
            parts.append(
                f"from_cache={bool(data['cache_hit'])} sim={sim if sim is not None else 'n/a'}"
            )
        trace = data.get("trace") or []
        for ev in trace[-6:]:  # last few breadcrumbs
            e = ev.get("event")
            meta = ev.get("meta", {})
            if e and isinstance(meta, dict):
                kv = ", ".join(f"{k}={v}" for k, v in meta.items())
                parts.append(f"{e}: {kv}")
        return " | ".join(parts)

    async def run(self, prompt: str, match: re.Match) -> str:
        rid = None
        if match.lastgroup == "rid":
            rid = match.group("rid")
        else:
            # try to extract from explicit parameter inside prompt
            m2 = re.search(r"req_id=([a-f0-9\-]{8,})", prompt, re.I)
            if m2:
                rid = m2.group(1)
        data = None
        if rid:
            data = _get(rid)
        if not data:
            items = _recent(1)
            data = items[0] if items else None
        return self._format(data)
