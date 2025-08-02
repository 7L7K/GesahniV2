from __future__ import annotations

import re
from .base import Skill
from ..home_assistant import get_states

class DeviceTrackerSkill(Skill):
    PATTERNS = [re.compile(r"is\s+([\w\s]+)\s+home\??", re.I)]

    async def run(self, prompt: str, match: re.Match) -> str:
        name = match.group(1).strip()
        states = await get_states()
        for st in states:
            eid = st.get("entity_id", "")
            if not eid.startswith("device_tracker."):
                continue
            friendly = st.get("attributes", {}).get("friendly_name", "")
            if name.lower() in {friendly.lower(), eid.split(".")[-1].replace("_", " ")}:
                state = st.get("state", "unknown").lower()
                if state == "home":
                    return f"{name} is home."
                if state in {"not_home", "away"}:
                    return f"{name} is away."
                return f"{name} is {state}."
        return f"I don't know where {name} is."
