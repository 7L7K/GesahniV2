from __future__ import annotations

import re
from typing import Dict, List

from pathlib import Path
from .base import Skill
from .ledger import record_action

_ROUTINES_PATH = Path("data/routines.json")


def _load_routines() -> Dict[str, List[str]]:
    try:
        import json

        return json.loads(_ROUTINES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_routines(r: Dict[str, List[str]]) -> None:
    try:
        import json

        _ROUTINES_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ROUTINES_PATH.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


class RoutineSkill(Skill):
    PATTERNS = [
        re.compile(r"create routine (?P<name>[\w\s]+): (?P<steps>.+)", re.I),
        re.compile(r"run (?P<name>[\w\s]+) now", re.I),
    ]

    async def run(self, prompt: str, match) -> str:
        gd = match.groupdict()
        if gd.get("steps") and gd.get("name"):
            name = gd["name"].strip()
            steps = [s.strip() for s in gd["steps"].split(";") if s.strip()]
            r = _load_routines()
            r[name] = steps
            _save_routines(r)
            await record_action("routine.create", idempotency_key=f"routine:create:{name}", metadata={"name": name, "steps": steps}, reversible=False)
            return f"Saved routine {name} with {len(steps)} steps."
        if gd.get("name"):
            name = gd["name"].strip()
            r = _load_routines()
            if name not in r:
                return f"No routine named {name}."
            # Execute steps best-effort: record only
            await record_action("routine.run", idempotency_key=f"routine:run:{name}:{int(__import__('time').time())}", metadata={"name": name, "steps": r[name]}, reversible=True)
            return f"Running routine {name} now: {', '.join(r[name])}"
        return "Could not parse routine command."


import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Skill
from .ledger import record_action

ROUTINES_DB = Path(__file__).resolve().parents[1] / "data" / "routines.json"
ROUTINES_DB.parent.mkdir(parents=True, exist_ok=True)


def _load_routines() -> dict:
    try:
        return json.loads(ROUTINES_DB.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_routines(d: dict) -> None:
    try:
        ROUTINES_DB.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


class RoutineSkill(Skill):
    PATTERNS = [
        re.compile(r"create routine (?P<name>[\w\s]+) with steps (?P<steps>.+)", re.I),
        re.compile(r"run routine (?P<rname>[\w\s]+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        gd = match.groupdict()
        if gd.get("name") and gd.get("steps"):
            name = gd["name"].strip()
            steps = [s.strip() for s in gd["steps"].split(",")]
            r = _load_routines()
            r[name] = {"steps": steps, "created_at": datetime.now().isoformat()}
            _save_routines(r)
            await record_action("routine.create", idempotency_key=f"routine:{name}", metadata={"steps": steps})
            return f"Routine '{name}' created with {len(steps)} steps."

        if gd.get("rname"):
            name = gd["rname"].strip()
            r = _load_routines()
            routine = r.get(name)
            if not routine:
                return f"No routine named {name}."
            # execute steps (best-effort: just record in ledger and notes)
            await record_action("routine.run", idempotency_key=f"routine:run:{name}:{int(datetime.now().timestamp()//10)}", metadata={"name": name})
            return f"Running routine '{name}': {', '.join(routine.get('steps', []))}"

        return "Could not parse routine command."

__all__ = ["RoutineSkill"]


