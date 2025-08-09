from __future__ import annotations

import os
import re
import httpx
import logging

from .base import Skill
from ..telemetry import log_record_var

log = logging.getLogger(__name__)

# basic currency name to code mapping
CODES = {
    "usd": "USD",
    "dollar": "USD",
    "dollars": "USD",
    "eur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "jpy": "JPY",
    "yen": "JPY",
    "gbp": "GBP",
    "pound": "GBP",
    "pounds": "GBP",
}


class CurrencySkill(Skill):
    PATTERNS = [
        re.compile(
            r"how many ([a-zA-Z]+) (?:is|are) (\d+(?:\.\d+)?) ([a-zA-Z]+)", re.I
        ),
        re.compile(r"(\d+(?:\.\d+)?) ([a-zA-Z]+) to ([a-zA-Z]+)", re.I),
        re.compile(r"convert (\d+(?:\.\d+)?) ([a-zA-Z]+) to ([a-zA-Z]+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        groups = match.groups()
        if len(groups) == 3 and "how many" in match.re.pattern:
            to_cur, amount, from_cur = groups
        elif len(groups) == 3 and "convert" in match.re.pattern:
            amount, from_cur, to_cur = groups
        else:
            amount, from_cur, to_cur = groups
        amount = float(amount)
        from_code = CODES.get(from_cur.lower(), from_cur.upper())
        to_code = CODES.get(to_cur.lower(), to_cur.upper())
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.exchangerate.host/convert",
                    params={"from": from_code, "to": to_code, "amount": amount},
                )
                resp.raise_for_status()
                data = resp.json()
                result = data.get("result")
                if result is None:
                    raise ValueError("no result")
        except Exception:
            log.exception("Currency conversion failed")
            return "Currency conversion failed."
        rec = log_record_var.get()
        if rec is not None:
            rec.route_reason = (rec.route_reason or "") + "|force_llama_currency"
        return f"{amount:.2f} {from_code} is {result:.2f} {to_code}."
