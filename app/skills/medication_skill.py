from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

from .base import Skill
from .ledger import record_action
from .notes_skill import dao as notes_dao


# DND window defaults (inclusive start hour, exclusive end hour)
def _parse_hour_env(val: str | None, default: int) -> int:
    if not val:
        return default
    try:
        # allow formats like "22" or "22:00"
        if ":" in val:
            return int(val.split(":")[0])
        return int(val)
    except Exception:
        return default


DND_START_HOUR = _parse_hour_env(__import__("os").environ.get("QUIET_HOURS_START"), 21)
DND_END_HOUR = _parse_hour_env(__import__("os").environ.get("QUIET_HOURS_END"), 7)

MED_DB = Path(__file__).resolve().parents[1] / "data" / "medications.json"
MED_DB.parent.mkdir(parents=True, exist_ok=True)


class MedicationSkill(Skill):
    """Medication reminders and taken/skipped logging.

    Behavior:
      - Respect DND (no non-urgent reminders between QUIET_HOURS_START..QUIET_HOURS_END).
      - Record taken/skipped events as notes and ledger entries.
      - Allow lightweight scheduling: "remind me to take X at 9am".
    """

    PATTERNS = [
        re.compile(r"remind me to take (?P<drug>[\w\s]+) at (?P<time>.+)", re.I),
        re.compile(r"i (?:took|took the) (?P<drug2>[\w\s]+)", re.I),
        re.compile(r"i skipped (?P<drug3>[\w\s]+)", re.I),
        re.compile(r"did i take (?P<drug4>[\w\s]+) (?:today)?\??", re.I),
    ]

    def _in_dnd(self) -> bool:
        now = datetime.now()
        h = now.hour
        if DND_START_HOUR <= DND_END_HOUR:
            return DND_START_HOUR <= h < DND_END_HOUR
        # overnight range (e.g., 21..7)
        return h >= DND_START_HOUR or h < DND_END_HOUR

    async def run(self, prompt: str, match: re.Match) -> str:
        gd = match.groupdict()

        # scheduling a reminder
        if gd.get("drug") and gd.get("time"):
            if self._in_dnd():
                return "It's quiet hours; please schedule this after the quiet period or mark it urgent."
            drug = gd["drug"].strip()
            when_text = gd["time"].strip()
            # naive time parse: hour extraction
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

        # logging taken/skipped/check
        drug = gd.get("drug2") or gd.get("drug3") or gd.get("drug4")
        if drug:
            drug = drug.strip()
            verb = "took" if gd.get("drug2") else ("skipped" if gd.get("drug3") else "checked")
            txt = f"Medication {verb}: {drug} @ {datetime.now().isoformat()}"
            try:
                await notes_dao.add(txt)
            except Exception:
                pass
            await record_action(
                "med.log",
                idempotency_key=f"medlog:{drug}:{int(datetime.now().timestamp()//10)}",
                metadata={"drug": drug, "verb": verb},
            )
            return f"Noted: {verb} {drug}."

        return "I couldn't parse that medication request."


__all__ = ["MedicationSkill"]


