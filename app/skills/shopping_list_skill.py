from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import List

from .base import Skill


_LIST_PATH = Path(os.getenv("SHOPPING_LIST_FILE", "data/shopping_list.json"))


def _load_list() -> List[str]:
    try:
        if _LIST_PATH.exists():
            data = json.loads(_LIST_PATH.read_text(encoding="utf-8") or "[]")
            if isinstance(data, list):
                return [str(x) for x in data]
    except Exception:
        pass
    return []


def _save_list(items: List[str]) -> None:
    try:
        _LIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        _LIST_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


class ShoppingListSkill(Skill):
    PATTERNS = [
        re.compile(r"\badd (?P<item>.+) to (?:my )?shopping list\b", re.I),
        re.compile(r"\bremove (?P<rem>.+) from (?:my )?shopping list\b", re.I),
        re.compile(r"\b(clear|empty) (?:my )?shopping list\b", re.I),
        re.compile(r"\b(?:show|list|what's on) (?:my )?shopping list\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        items = _load_list()
        gd = match.groupdict()
        if gd.get("item"):
            item = gd["item"].strip()
            if item:
                items.append(item)
                _save_list(items)
                return f"Added {item} to your shopping list."
        if gd.get("rem"):
            rem = gd["rem"].strip().lower()
            new_items = [x for x in items if x.lower() != rem]
            if len(new_items) == len(items):
                return f"Couldn't find {rem} on your list."
            _save_list(new_items)
            return f"Removed {rem} from your shopping list."
        if re.search(r"\b(clear|empty) ", prompt, re.I):
            _save_list([])
            return "Shopping list cleared."
        if not items:
            return "Your shopping list is empty."
        return "; ".join(items)


