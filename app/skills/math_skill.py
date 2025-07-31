from __future__ import annotations
import re
from typing import Optional
from .base import Skill

class MathSkill(Skill):
    PATTERNS = [
        re.compile(r"(?P<a>\d+(?:\.\d+)?)\s*(?P<op>[+\-*/x×])\s*(?P<b>\d+(?:\.\d+)?)", re.I),
        re.compile(r"(?P<pct>\d+(?:\.\d+)?)%\s*of\s*(?P<of>\d+(?:\.\d+)?)", re.I),
        re.compile(r"round\s+(?P<val>\d+(?:\.\d+)?)\s+to\s+(?P<places>\d+)\s+decimal", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        d = match.groupdict()
        if "op" in d and d["op"]:
            a = float(d["a"])
            b = float(d["b"])
            op = d["op"].lower()
            if op in {"x", "×", "*"}:
                res = a * b
            elif op == "/":
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

    async def handle(self, prompt: str) -> str:
        for pat in self.PATTERNS:
            match = pat.search(prompt)
            if match:
                return await self.run(prompt, match)
        return "Sorry, I couldn't understand that math problem."
