# app/skills/entities_skill.py
from __future__ import annotations

import re
from .base import Skill
from .. import home_assistant as ha


class EntitiesSkill(Skill):
    """
    Responds to queries like:
      • “list lights”
      • “show all switches”
      • “list Home Assistant entities page 2”
    Returns up to 50 results per page; users can request next pages.
    """

    PATTERNS = [
        re.compile(
            r"\b(?:list|show)\s+"  # list / show
            r"(?:all\s+)?"  # optional “all”
            r"(?:home\s*assistant\s+)?"  # optional “home assistant”
            r"(?P<kind>entities|lights|switches)"  # the thing we’re listing
            r"(?:\s+page\s+(?P<page>\d+))?"  # optional “page N”
            r"\b",
            re.I,
        )
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        kind = match.group("kind").lower()  # entities / lights / switches
        page = int(match.group("page") or 1)
        PAGE_SIZE = 50
        start, end = (page - 1) * PAGE_SIZE, page * PAGE_SIZE

        # grab all HA states
        states = await ha.get_states()

        # narrow to requested domain
        domain_prefix = {"lights": "light.", "switches": "switch."}.get(kind, "")
        wanted = (
            [s for s in states if s["entity_id"].startswith(domain_prefix)]
            if domain_prefix
            else states
        )

        if not wanted:
            return f"No {kind} found."

        # build nicely‑formatted lines for this slice
        lines = [
            f'{s["attributes"].get("friendly_name", "-")} → {s["entity_id"]}'
            for s in wanted[start:end]
        ]
        body = "\n".join(lines)

        # append pagination hint if we truncated results
        if len(wanted) > end:
            body += (
                f"\n… and {len(wanted) - end} more. "
                f"Ask “list {kind} page {page + 1}” for the next page."
            )

        header = (
            f"Here are the {kind} I see:"
            if domain_prefix
            else f"Here are some entities (page {page}):"
        )
        return f"{header}\n{body}"
