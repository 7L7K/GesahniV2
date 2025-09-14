# app/skills/teach_skill.py
import re

from .. import alias_store
from .. import home_assistant as ha
from ..telemetry import log_record_var
from .base import Skill
from .ledger import record_action


class TeachSkill(Skill):
    PATTERNS = [re.compile(r"^my (.+?) is (.+)$", re.I)]

    async def run(self, prompt, m):
        alias, actual = m.group(1), m.group(2)
        results = await ha.resolve_entity(actual)
        if not results:
            raise ValueError("entity not found")
        entity = results[0]
        await alias_store.set(alias, entity)
        # Record alias training as idempotent
        idemp = f"alias:{alias}:{entity}"
        await record_action(
            "alias.set",
            idempotency_key=idemp,
            metadata={"alias": alias, "entity": entity},
        )
        rec = log_record_var.get()
        if rec is not None:
            rec.route_reason = (rec.route_reason or "") + "|alias_saved"
        return f"Got it – when you say “{alias}” I’ll use {entity}."
