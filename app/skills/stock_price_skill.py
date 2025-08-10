from __future__ import annotations

import os
import re
import httpx
import logging

from .base import Skill

log = logging.getLogger(__name__)

ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY")


class StockPriceSkill(Skill):
    PATTERNS = [
        re.compile(r"\bstock price of ([A-Za-z]{1,5})\b", re.I),
        re.compile(r"\b([A-Za-z]{1,5}) quote\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        ticker = match.group(1).upper()
        if not ALPHAVANTAGE_KEY:
            return "Stock API key not set."
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://www.alphavantage.co/query",
                    params={
                        "function": "GLOBAL_QUOTE",
                        "symbol": ticker,
                        "apikey": ALPHAVANTAGE_KEY,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                price_str = data.get("Global Quote", {}).get("05. price")
                if price_str is None:
                    raise ValueError("price missing")
                price = float(price_str)
        except Exception:
            log.exception("Stock price fetch failed")
            return f"Couldn't get price for {ticker}."
        return f"{ticker} is ${price:.2f}."
