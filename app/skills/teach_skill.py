# app/skills/teach_skill.py
import re
from .base import Skill
from .. import home_assistant as ha
from .. import alias_store
from ..telemetry import log_record_var


class TeachSkill(Skill):
    PATTERNS = [re.compile(r"^my (.+?) is (.+)$", re.I)]

    async def run(self, prompt, m):
        alias, actual = m.group(1), m.group(2)
        results = await ha.resolve_entity(actual)
        if not results:
            raise ValueError("entity not found")
        entity = results[0]
        await alias_store.set(alias, entity)
        rec = log_record_var.get()
        if rec is not None:
            rec.route_reason = (rec.route_reason or "") + "|alias_saved"
        return f"Got it – when you say “{alias}” I’ll use {entity}."
