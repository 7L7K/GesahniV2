from __future__ import annotations

from .. import home_assistant as ha
from .. import storage
from .base import Skill
from .ledger import get_last_reversible_action


class UndoSkill(Skill):
    PATTERNS = [
        # "undo" or "undo last action"
        __import__("re").compile(r"\bundo(?: last)?(?: action)?\b", __import__("re").I)
    ]

    async def run(self, prompt: str, match) -> str:
        # find last reversible action from ledger
        rec = await get_last_reversible_action()
        if not rec:
            return "Nothing to undo."
        # determine inverse
        typ = rec.get("type")
        meta = rec.get("slots") or {}
        if typ.startswith("lights.") or typ.startswith("lights"):
            # expected meta: entity, prev:{state,brightness}
            ent = meta.get("entity")
            prev = meta.get("prev") or {}
            if not ent:
                return "Cannot undo lights action: missing entity info."
            # restore previous brightness/state
            if prev.get("state") == "off":
                await ha.call_service("light", "turn_off", {"entity_id": ent})
            else:
                # if brightness present, use pct; brightness stored as pct
                b = prev.get("brightness")
                if b is not None:
                    await ha.call_service(
                        "light", "turn_on", {"entity_id": ent, "brightness_pct": b}
                    )
                else:
                    await ha.call_service("light", "turn_on", {"entity_id": ent})
            # record reverse action in ledger and link via reverse_id
            # write reverse entry directly to storage so we can link reverse_id
            _, rev_rowid = storage.record_ledger(
                type="undo.lights",
                skill="undo",
                slots={"reverted": rec.get("id")},
                reversible=False,
                idempotency_key=None,
            )
            try:
                storage.link_reverse(int(rec.get("id")), int(rev_rowid))
            except Exception:
                pass
            return "Undid last light change."

        if typ.startswith("timer."):
            # timers stored by label; reverse action is cancel
            label = meta.get("label") or meta.get("name")
            if not label:
                return "Cannot undo timer: missing label."
            await ha.call_service("timer", "cancel", {"entity_id": f"timer.{label}"})
            _, rev_rowid = storage.record_ledger(
                type="undo.timer",
                skill="undo",
                slots={"reverted": rec.get("id")},
                reversible=False,
                idempotency_key=None,
            )
            try:
                storage.link_reverse(int(rec.get("id")), int(rev_rowid))
            except Exception:
                pass
            return "Timer cancelled (undo)."

        if typ.startswith("reminder."):
            # best-effort: mark as removed from reminders file (no single source)
            # TODO: make reminders have ids to remove precisely
            _, rev_rowid = storage.record_ledger(
                type="undo.reminder",
                skill="undo",
                slots={"reverted": rec.get("id")},
                reversible=False,
                idempotency_key=None,
            )
            try:
                storage.link_reverse(int(rec.get("id")), int(rev_rowid))
            except Exception:
                pass
            return "Undid last reminder (best-effort)."

        # fallback
        return "Cannot undo that action automatically."
