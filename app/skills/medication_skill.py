from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .base import Skill
from .ledger import record_action
from .notes_skill import dao as notes_dao


MED_DB = Path(__file__).resolve().parents[1] / "data" / "medications.json"
MED_DB.parent.mkdir(parents=True, exist_ok=True)


class MedicationSkill(Skill):
    """Simple medication reminders and taken/skipped logging.

    - Patterns:
      - "remind me to take <drug> at 9am"
      - "I took <drug>" / "I skipped <drug>"
      - "did I take <drug> today?"
    """

    PATTERNS = [
        re.compile(r"remind me to take (?P<drug>[\w\s]+) at (?P<time>.+)", re.I),
        re.compile(r"i (?:took|took the) (?P<drug2>[\w\s]+)", re.I),
        re.compile(r"i skipped (?P<drug3>[\w\s]+)", re.I),
        re.compile(r"did i take (?P<drug4>[\w\s]+) (?:today)?\??", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        gd = match.groupdict()
        # schedule reminder (very crude time handling)
        if gd.get("drug") and gd.get("time"):
            drug = gd["drug"].strip()
            when_text = gd["time"].strip()
            # naive: if time contains digits assume today at that hour
            try:
                hh = int(re.search(r"(\d{1,2})", when_text).group(1))
                now = datetime.now()
                run_at = now.replace(hour=hh, minute=0, second=0, microsecond=0)
                if run_at < now:
                    run_at = run_at + timedelta(days=1)
            except Exception:
                run_at = datetime.now() + timedelta(hours=1)

            idemp = f"med:{drug}:{int(run_at.timestamp())}"
            await record_action("med.reminder", idempotency_key=idemp, metadata={"drug": drug, "when": run_at.isoformat()})
            return f"Reminder set to take {drug} at {run_at.strftime('%Y-%m-%d %I:%M %p')}"

        # logging taken
        drug = gd.get("drug2") or gd.get("drug3") or gd.get("drug4")
        if drug:
            drug = drug.strip()
            verb = "took" if gd.get("drug2") else ("skipped" if gd.get("drug3") else "checked")
            # write a short note for record
            txt = f"Medication {verb}: {drug} @ {datetime.now().isoformat()}"
            try:
                await notes_dao.add(txt)
            except Exception:
                pass
            await record_action("med.log", idempotency_key=f"medlog:{drug}:{int(datetime.now().timestamp()//10)}", metadata={"drug": drug, "verb": verb})
            return f"Noted: {verb} {drug}."

        return "I couldn't parse that medication request."


__all__ = ["MedicationSkill"]


