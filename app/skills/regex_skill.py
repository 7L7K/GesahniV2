from __future__ import annotations

import re

from .base import Skill


class RegexExplainSkill(Skill):
    PATTERNS = [
        re.compile(r"^explain regex:\s*(?P<pattern>.+)$", re.I),
        re.compile(r"^test regex:\s*(?P<pattern>.+?)\s+on\s+(?P<input>.+)$", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        gd = match.groupdict()
        if "input" in gd and gd.get("input"):
            pattern = gd.get("pattern") or ""
            text = gd.get("input") or ""
            try:
                m = re.search(pattern, text)
                if not m:
                    return "no match"
                if m.groups():
                    groups = ", ".join(f"{i}:{g}" for i, g in enumerate(m.groups(), start=1))
                    return f"matched: {m.group(0)} | groups: {groups}"
                return f"matched: {m.group(0)}"
            except re.error as e:
                return f"invalid regex: {e}"
        pattern = gd.get("pattern") or ""
        try:
            re.compile(pattern)
        except re.error as e:
            return f"invalid regex: {e}"
        # Lightweight human hint (not full LM explain):
        hints = []
        if pattern.startswith("^"):
            hints.append("anchors at start")
        if pattern.endswith("$"):
            hints.append("anchors at end")
        if "(?P<" in pattern:
            hints.append("named groups present")
        if "|" in pattern:
            hints.append("alternation")
        if not hints:
            hints.append("valid regex")
        return ", ".join(hints)


