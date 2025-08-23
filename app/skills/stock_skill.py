from __future__ import annotations

import logging
import re

import httpx

from .base import Skill
from .currency_skill import CODES as CURRENCY_CODES

log = logging.getLogger(__name__)

SYMBOLS = {
    "btc": "BTC-USD",
    "bitcoin": "BTC-USD",
}


class StockSkill(Skill):
    PATTERNS = [
        re.compile(r"stock price for ([a-zA-Z0-9.\-]+)(?: in ([a-zA-Z]{3}))?", re.I),
        re.compile(r"([a-zA-Z0-9.\-]+) price(?: in ([a-zA-Z]{3}))?", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        ticker, to_cur = match.groups()
        symbol = SYMBOLS.get(ticker.lower(), ticker.upper())
        display = ticker.upper()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(
                    "https://query1.finance.yahoo.com/v7/finance/quote",
                    params={"symbols": symbol},
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("quoteResponse", {}).get("result", [])
                if not results:
                    raise ValueError("no quote")
                quote = results[0]
                price = quote.get("regularMarketPrice")
                currency = quote.get("currency") or "USD"
                if price is None:
                    raise ValueError("no price")
                if to_cur:
                    to_code = CURRENCY_CODES.get(to_cur.lower(), to_cur.upper())
                    if to_code != currency:
                        c = await client.get(
                            "https://api.exchangerate.host/convert",
                            params={"from": currency, "to": to_code, "amount": price},
                        )
                        c.raise_for_status()
                        c_data = c.json()
                        price = c_data.get("result")
                        if price is None:
                            raise ValueError("conversion failed")
                        currency = to_code
            return f"{display} is {price:.2f} {currency}"
        except Exception:
            log.exception("Stock price lookup failed")
            return "Stock price lookup failed."
