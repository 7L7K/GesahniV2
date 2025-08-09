from __future__ import annotations

import re
from typing import Callable, Dict, Tuple

from .base import Skill
from ..telemetry import log_record_var


# simple conversion functions
def _l_to_oz(x: float) -> float:
    return x * 33.814


def _oz_to_l(x: float) -> float:
    return x * 0.0295735


def _c_to_f(x: float) -> float:
    return x * 9 / 5 + 32


def _f_to_c(x: float) -> float:
    return (x - 32) * 5 / 9


def _km_to_mi(x: float) -> float:
    return x * 0.621371


def _mi_to_km(x: float) -> float:
    return x * 1.60934


CONVERSIONS: Dict[Tuple[str, str], Callable[[float], float]] = {
    ("liter", "ounce"): _l_to_oz,
    ("ounce", "liter"): _oz_to_l,
    ("c", "f"): _c_to_f,
    ("f", "c"): _f_to_c,
    ("kilometer", "mile"): _km_to_mi,
    ("mile", "kilometer"): _mi_to_km,
}


class UnitConversionSkill(Skill):
    PATTERNS = [
        re.compile(r"how many ([a-zA-Z]+) in (\d+(?:\.\d+)?) ([a-zA-Z]+)", re.I),
        re.compile(r"(\d+(?:\.\d+)?)\s*°?\s*(c|f)\s*to\s*(c|f)", re.I),
        re.compile(r"convert (\d+(?:\.\d+)?) ([a-zA-Z]+) to ([a-zA-Z]+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        groups = match.groups()
        if len(groups) == 3 and "how many" in match.re.pattern:
            to_unit, amount, from_unit = groups
        elif len(groups) == 3 and "convert" in match.re.pattern:
            amount, from_unit, to_unit = groups
        elif len(groups) == 3:
            amount, from_unit, to_unit = groups
        else:
            return "Unsupported conversion."

        amount = float(amount)
        from_unit = from_unit.lower().rstrip("s")
        to_unit = to_unit.lower().rstrip("s")
        func = CONVERSIONS.get((from_unit, to_unit))
        if not func:
            return "Conversion not supported."
        result = func(amount)
        rec = log_record_var.get()
        if rec is not None:
            rec.route_reason = (rec.route_reason or "") + "|force_llama_convert"
        return f"{amount:g} {from_unit}{'' if amount==1 else 's'} is {result:.2f} {to_unit}{'' if result==1 else 's'}."
