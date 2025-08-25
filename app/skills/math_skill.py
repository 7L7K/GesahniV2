from __future__ import annotations

import re

from ..telemetry import log_record_var
from .base import Skill
from .math_eval import evaluate_expr, EvalError


class MathSkill(Skill):
    PATTERNS = [
        re.compile(
            r"(?P<a>\d+(?:\.\d+)?)\s*(?P<op>[+\-*/x×])\s*(?P<b>\d+(?:\.\d+)?)", re.I
        ),
        re.compile(r"(?P<pct>\d+(?:\.\d+)?)%\s*of\s*(?P<of>\d+(?:\.\d+)?)", re.I),
        re.compile(
            r"round\s+(?P<val>\d+(?:\.\d+)?)\s+to\s+(?P<places>\d+)\s+decimal", re.I
        ),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        # Use safe AST evaluator for arithmetic and comparisons
        expr = prompt.strip()
        try:
            val, expl = evaluate_expr(expr)
        except EvalError as e:
            # Fall back to existing simple patterns for backwards compatibility
            d = match.groupdict()
            if "op" in d and d["op"]:
                a = float(d["a"])
                b = float(d["b"])
                op = d["op"].lower()
                if op in {"x", "×", "*"}:
                    res = a * b
                elif op == "/":
                    if b == 0:
                        return "Cannot divide by zero"
                    res = a / b
                elif op == "+":
                    res = a + b
                else:
                    res = a - b
                if res.is_integer():
                    res = int(res)
                return str(res)
            if "pct" in d and d["pct"]:
                pct = float(d["pct"])
                of = float(d["of"])
                res = of * (pct / 100.0)
                return str(round(res, 2))
            if "val" in d:
                val = float(d["val"])
                places = int(d["places"])
                return str(round(val, places))
            return "Could not compute"

        # Produce safe, typed output
        rec = log_record_var.get()
        if rec is not None:
            rec.route_reason = (rec.route_reason or "") + "|safe_math"

        # If boolean, return boolean with explanation and user-friendly wording
        if isinstance(val, bool):
            detail = expl.split(':', 1)[-1].strip()
            # If the boolean was produced from an approximate rewrite, the detail
            # may be an expression like "abs((1/3)-(0.3333333)) <= 1e-09"; make
            # a short human-friendly explanation.
            if detail.startswith("abs("):
                return f"{val} — because numbers differ by <= {EPS}"
            return f"{val} — because {detail}"
        # If numeric, format reasonably
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        return f"{val} — {expl}"

    async def handle(self, prompt: str) -> str:
        # First try simple regex matches for backward compatibility
        for pat in self.PATTERNS:
            match = pat.search(prompt)
            if match:
                try:
                    return await self.run(prompt, match)
                except Exception:
                    return "I couldn't parse that as math. Try like: 3*3=9, 2^3, sqrt(16)."

        # If no pattern matched, attempt safe AST evaluation on the whole prompt
        try:
            val, expl = evaluate_expr(prompt)
        except EvalError:
            return "I couldn't parse that as math. Try like: 3*3=9, 2^3, sqrt(16)."
        # Format boolean vs numeric
        if isinstance(val, bool):
            return f"{val} — because {expl.split(':',1)[-1].strip()}"
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        return f"{val} — {expl}"
