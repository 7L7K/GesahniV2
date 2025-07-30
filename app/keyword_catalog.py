from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Type, Dict, List

from .skills import MathSkill, TranslateSkill, SearchSkill, TimerSkill, NotesSkill
from .skills.base import Skill, _normalize
from .history import append_history
from .telemetry import log_record_var


CATALOG_PATH = Path(__file__).parent / "skills" / "keyword_catalog.json"

_SKILL_CLASSES: Dict[str, Type[Skill]] = {
    "MathSkill": MathSkill,
    "TranslateSkill": TranslateSkill,
    "SearchSkill": SearchSkill,
    "TimerSkill": TimerSkill,
    "NotesSkill": NotesSkill,
}


def _load_catalog() -> Dict[Type[Skill], List[str]]:
    with CATALOG_PATH.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    cat: Dict[Type[Skill], List[str]] = {}
    for name, words in raw.items():
        cls = _SKILL_CLASSES.get(name)
        if cls is not None:
            cat[cls] = [w.lower() for w in words]
    return cat


KEYWORD_CATALOG = _load_catalog()


async def check_keyword_catalog(prompt: str) -> Optional[str]:
    """Return skill response if prompt matches keyword catalog."""
    norm = _normalize(prompt)
    low = norm.lower()
    for cls, keywords in KEYWORD_CATALOG.items():
        if any(k in low for k in keywords):
            skill = cls()
            m = skill.match(norm)
            if not m:
                continue
            resp = await skill.run(prompt, m)
            rec = log_record_var.get()
            if rec is not None:
                rec.matched_skill = cls.__name__
                rec.match_confidence = 1.0
                rec.engine_used = cls.__name__
                rec.response = str(resp)
            await append_history(prompt, cls.__name__, str(resp))
            return resp
    return None
