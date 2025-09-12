from __future__ import annotations

import re

from .. import home_assistant as ha
from .base import Skill


class DoorLockSkill(Skill):
    PATTERNS = [
        re.compile(r"\b(lock|unlock) ([\w\s]+) door\b", re.I),
        re.compile(r"\bis ([\w\s]+) door locked\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        if match.re.pattern.startswith("\\b(lock|unlock)"):
            action, name = match.group(1), match.group(2)
            # resolve via parsers.resolve_entity to enforce alias-first and disambiguation
            from .parsers import resolve_entity
            res = await resolve_entity(name, kind="lock")
            if res.get("action") == "disambiguate":
                return "Which door did you mean? I found multiple matches."
            entity = res.get("entity_id")
            # validate lock action
            from .tools.validator import validate_entity_resolution, validate_lock_action

            ok, expl, confirm = validate_entity_resolution({"entity_id": entity, "friendly_name": res.get("friendly_name"), "confidence": res.get("confidence")})
            if not ok:
                return expl
            ok, expl, confirm = validate_lock_action(action)
            if not ok:
                if confirm:
                    return "Action requires confirmation."
                return expl
            await ha.call_service(
                "lock",
                "lock" if action == "lock" else "unlock",
                {"entity_id": entity},
            )
            return f"{action.title()}ed {entity}"
        name = match.group(1)
        results = await ha.resolve_entity(name)
        if not results:
            return f"I couldn't find “{name}”."
        entity = results[0]
        return f"{entity} is locked"  # simplified
