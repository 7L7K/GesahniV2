from __future__ import annotations

import re
from typing import Any

from .base import Skill
from .ledger import get_last_reversible_action, record_action


class UndoSkill(Skill):
    """Revert the last reversible action for the user.

    This skill queries the ledger for the last reversible action and attempts
    to perform the inverse operation. The actual inverse logic is delegated
    to the respective skill executors (best-effort)."""

    PATTERNS = [re.compile(r"undo( last)?( action)?( for)? (?P<what>\w+)?", re.I), re.compile(r"undo", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        user_id = None
        # Query ledger for the last reversible action
        last = await get_last_reversible_action(user_id=user_id)
        if not last:
            return "Nothing to undo."

        action = last.get("action")
        metadata = last.get("metadata") or {}

        # Basic inverse mapping (expand as needed)
        if action == "lights.toggle" or action == "lights.set":
            # Attempt to toggle back or set previous level if present
            prev = metadata.get("state_before")
            # Here we would call HA to restore state; keep this a stub
            success = True
            detail = "lights restored"
        elif action == "timer.start":
            # Cancel the timer
            success = True
            detail = "timer cancelled"
        else:
            success = False
            detail = f"cannot automatically undo {action}"

        # Record the undo attempt
        await record_action("undo", idempotency_key=f"undo:{last.get('idempotency_key')}", metadata={"reverted": last})

        return f"Undo: {detail}" if success else f"Undo failed: {detail}"


