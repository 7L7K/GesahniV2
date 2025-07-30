from __future__ import annotations

import re

from .base import Skill


class MathSkill(Skill):
    """Basic arithmetic and rounding."""

    PATTERNS = [
        re.compile(r"^(?P<expr>[0-9x×+\-*/\.\s]+)$", re.I),
        re.compile(r"(?P<pct>\d+(?:\.\d+)?)% of (?P<num>\d+(?:\.\d+)?)", re.I),
        re.compile(r"round (?P<val>\d+(?:\.\d+)?)(?: to (?P<places>\d+))?", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.groupdict().get("pct"):
            pct = float(match.group("pct"))
            num = float(match.group("num"))
            return str(pct * num / 100)
        if match.groupdict().get("val"):
            val = float(match.group("val"))
            places = int(match.group("places")) if match.group("places") else 0
            return str(round(val, places))
        expr = match.group("expr").replace("×", "*").replace("x", "*")
        try:
            # safe eval by restricting allowed characters
            if not re.fullmatch(r"[0-9+\-*/.\s]+", expr):
                return "Invalid expression"
            result = eval(expr)
        except Exception:
            return "Invalid expression"
        if isinstance(result, float) and result.is_integer():
            result = int(result)
        return str(result)
