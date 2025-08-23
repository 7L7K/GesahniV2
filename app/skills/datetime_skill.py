from __future__ import annotations

import re
from datetime import datetime, timedelta

from .base import Skill


class DateTimeSkill(Skill):
    PATTERNS = [
        re.compile(r"\bwhat(?:'s| is)? today'?s date\b", re.I),
        re.compile(r"\bwhat day is it\b", re.I),
        re.compile(r"\bwhat(?:'s| is)? the date (?:tomorrow|yesterday)\b", re.I),
        re.compile(
            r"\bwhat(?:'s| is)? the date on (?P<delta>\d+) days from now\b", re.I
        ),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        p = prompt.lower().strip()
        now = datetime.now()
        if "today" in p or "what day is it" in p:
            return now.strftime("%A, %Y-%m-%d")
        if "tomorrow" in p:
            return (now + timedelta(days=1)).strftime("%A, %Y-%m-%d")
        if "yesterday" in p:
            return (now - timedelta(days=1)).strftime("%A, %Y-%m-%d")
        if match and match.groupdict().get("delta"):
            days = int(match.group("delta"))
            return (now + timedelta(days=days)).strftime("%A, %Y-%m-%d")
        return now.strftime("%Y-%m-%d")
