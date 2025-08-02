from __future__ import annotations

import re
import httpx
from .base import Skill

class StockSkill(Skill):
    PATTERNS = [re.compile(r"what(?:'s| is)\s+([A-Z]{1,5})\s+at\??", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        symbol = match.group(1).upper()
        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(url, params={"symbols": symbol})
                resp.raise_for_status()
                data = resp.json()
                price = data.get("quoteResponse", {}).get("result", [{}])[0].get("regularMarketPrice")
                if price is not None:
                    return f"{symbol} is at ${price:.2f}"
        except Exception:
            pass
        return f"Couldn't fetch price for {symbol}."
