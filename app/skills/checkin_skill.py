from __future__ import annotations

import re
from datetime import datetime, timedelta

from .base import Skill
from .ledger import record_action


class CheckinSkill(Skill):
    PATTERNS = [re.compile(r"check in( now)?(?: to (?P<topic>.+))?", re.I), re.compile(r"reschedule (?P<mins>\d+) minutes", re.I)]

    async def run(self, prompt: str, match) -> str:
        gd = match.groupdict()
        if gd.get("mins"):
            mins = int(gd["mins"])
            # write a template note with reschedule info
            await record_action("checkin.reschedule", idempotency_key=f"checkin:resched:{int(datetime.now().timestamp())}", metadata={"mins": mins}, reversible=False)
            return f"Rescheduled check-in by {mins} minutes."
        topic = gd.get("topic") or "general"
        # create template note
        await record_action("checkin.note", idempotency_key=f"checkin:note:{int(datetime.now().timestamp())}", metadata={"topic": topic}, reversible=False)
        return f"Noted a check-in for {topic}. You can say 'reschedule 30 minutes' to move it."


import re
from datetime import datetime, timedelta

from .base import Skill
from .notes_skill import dao as notes_dao
from .ledger import record_action


class CheckinSkill(Skill):
    PATTERNS = [
        re.compile(r"schedule a check-?in with (?P<person>[\w\s]+) (?:at|on) (?P<time>.+)", re.I),
        re.compile(r"check in with (?P<person2>[\w\s]+)", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        gd = match.groupdict()
        person = gd.get("person") or gd.get("person2")
        if not person:
            return "Who should I check in with?"
        person = person.strip()
        # naive schedule: ask later or record immediate note
        txt = f"Scheduled check-in with {person} requested at {datetime.now().isoformat()}"
        try:
            await notes_dao.add(txt)
        except Exception:
            pass
        await record_action("checkin.schedule", idempotency_key=f"checkin:{person}:{int(datetime.now().timestamp()//10)}", metadata={"person": person})
        return f"Check-in scheduled with {person}."

__all__ = ["CheckinSkill"]


