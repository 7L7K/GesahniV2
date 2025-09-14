from __future__ import annotations

import re

from .base import Skill
from .ledger import record_action
from .tools.confirmation import dequeue


class ConfirmationSkill(Skill):
    PATTERNS = [re.compile(r"^confirm (?P<key>[\w:-]+) (yes|no)$", re.I)]

    async def run(self, prompt: str, match) -> str:
        gd = match.groupdict()
        key = gd.get("key")
        if not key:
            return "Which confirmation?"
        if prompt.strip().lower().endswith(" yes"):
            payload = dequeue(key)
            if not payload:
                return "No pending action or it expired."
            # Execute stored payload (best-effort simple schema)
            tool = payload.get("tool")
            slots = payload.get("slots")
            # We expect validate_and_execute to exist in catalog
            from .tools.catalog import validate_and_execute

            ok, msg, confirm = await validate_and_execute(tool, slots)
            await record_action(
                "confirmation.accepted",
                idempotency_key=key,
                metadata={"tool": tool, "ok": ok},
            )
            return msg
        else:
            # decline
            dequeue(key)
            await record_action(
                "confirmation.declined", idempotency_key=key, metadata={}
            )
            return "Okay, cancelled."
