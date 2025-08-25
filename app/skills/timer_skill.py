from __future__ import annotations

import json
import os
import re
import time
from datetime import timedelta
from pathlib import Path

from .. import home_assistant as ha
from .base import Skill
from .ledger import record_action
from .parsers import parse_duration

TIMERS: dict[str, float] = {}
_TIMERS_STORE = Path(os.getenv("TIMERS_STORE", "data/timers.json"))


def _persist_timers() -> None:
    try:
        _TIMERS_STORE.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v for k, v in TIMERS.items()}
        _TIMERS_STORE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:  # pragma: no cover - best effort
        pass


class TimerSkill(Skill):
    PATTERNS = [
        # pat1: "start/set/create <name?> timer for <n> <unit>" (name before duration)
        re.compile(
            r"\b(?:start|set|begin|create) (?:(?P<name>[\w\-]+) )?timer for (?P<amount>\d+) (?P<unit>seconds?|second|minutes?|minute|mins?|hrs?|hours?)\b",
            re.I,
        ),
        # pat2: "create a timer for <n> <unit> named <name>" (name after duration)
        re.compile(
            r"\b(?:start|set|begin|create) (?:a )?timer for (?P<amount>\d+) (?P<unit>seconds?|second|minutes?|minute|mins?|hrs?|hours?)(?: (?:named|called) (?P<name>[\w\-]+))?\b",
            re.I,
        ),
        # pat2b: "set a timer named <name> for <n> <unit>" (name before duration using 'named')
        re.compile(
            r"\b(?:start|set|begin|create) (?:a )?timer (?:named|called) (?P<name>[\w\-]+) for (?P<amount>\d+) (?P<unit>seconds?|second|minutes?|minute|mins?|hrs?|hours?)\b",
            re.I,
        ),
        # pat3: "pause/resume/cancel <name?> timer" (singular/plural handling)
        re.compile(r"\b(?:pause|resume|cancel|stop) (?:(?P<cname>[\w\-]+) )?timers?\b", re.I),
        # how long left on <name?> timer
        re.compile(r"\bhow (?:much |long )?left (?:on|for) (?:(?P<qname>[\w\-]+) )?timers?\b", re.I),
    ]

    async def run(self, prompt: str, match: re.Match) -> str:
        groups = match.groupdict()
        # Normalize cleaned names (drop stopwords like 'the', 'my', trailing 's')
        def _clean_name(n: str | None) -> str:
            if not n:
                return "gesahni"
            s = n.strip().lower()
            # drop common stopwords
            s = re.sub(r"^(the|my|a|an)\s+", "", s)
            # drop trailing plural s for nicknames
            if s.endswith("s"):
                s = s[:-1]
            # replace spaces with underscore for entity id compatibility
            s = re.sub(r"\s+", "_", s)
            return s or "gesahni"

        if "cname" in groups and groups["cname"] is not None:
            name = _clean_name(groups["cname"]) or "gesahni"
            # extract first verb
            action = match.group(0).split()[0].lower()
            if action == "pause":
                await ha.call_service("timer", "pause", {"entity_id": f"timer.{name}"})
                # record ledger entry
                await record_action("timer.pause", idempotency_key=f"timer:{name}:pause")
                return f"{name} timer paused."
            if action == "resume":
                await ha.call_service("timer", "start", {"entity_id": f"timer.{name}"})
                await record_action("timer.resume", idempotency_key=f"timer:{name}:resume")
                return f"{name} timer resumed."
            if action == "stop":
                await ha.call_service("timer", "cancel", {"entity_id": f"timer.{name}"})
                TIMERS.pop(name, None)
                _persist_timers()
                await record_action("timer.cancel", idempotency_key=f"timer:{name}:cancel")
                return f"{name} timer cancelled."
            await ha.call_service("timer", "cancel", {"entity_id": f"timer.{name}"})
            TIMERS.pop(name, None)
            _persist_timers()
            return f"{name} timer cancelled."

        if "qname" in groups and groups["qname"] is not None:
            name = _clean_name(groups["qname"]) or "gesahni"
            if name not in TIMERS:
                return "No such timer."
            remaining = int(TIMERS[name] - time.monotonic())
            return f"{max(0, remaining)} seconds left on {name} timer."

        name = _clean_name(groups.get("name")) or "gesahni"
        amount = groups.get("amount")
        unit = (groups.get("unit") or "").lower()
        # Normalize units to common forms expected by parse_duration
        unit = re.sub(r"^hrs?$", "hours", unit)
        unit = re.sub(r"^mins?$", "minutes", unit)
        unit = re.sub(r"^seconds?$", "seconds", unit)
        total_seconds = parse_duration(amount, unit) or 0
        duration = str(timedelta(seconds=total_seconds))
        # Before calling service, validate duration
        from .tools.validator import validate_duration

        ok, expl, confirm = validate_duration(total_seconds)
        if not ok:
            if confirm:
                # enqueue confirmation
                key = f"confirm:timer:{int(time.time())}"
                from .tools.confirmation import enqueue

                enqueue(key, {"tool": "timer.start", "slots": {"label": name, "duration_s": total_seconds}}, ttl=30)
                return f"Do you want to start the timer for {total_seconds} seconds? Reply 'confirm {key} yes' to proceed."
            return expl

        await ha.call_service(
            "timer",
            "start",
            {"entity_id": f"timer.{name}", "duration": duration},
        )
        TIMERS[name] = time.monotonic() + total_seconds
        _persist_timers()
        # idempotency key buckets by rounding to nearest 10s to avoid
        # duplicate rapid re-requests
        bucket = int(time.time() // 10)
        idemp = f"timer:{name}:start:{bucket}"
        # Set skill_why for observability
        self.skill_why = f"timer.start: duration_s={total_seconds}"
        inserted = await record_action(
            "timer.start",
            idempotency_key=idemp,
            metadata={"duration_s": total_seconds, "label": name},
            reversible=True,
        )
        # store reverse_id when available in ledger (best-effort)
        # storage.record_ledger returns (inserted, rowid) at lower layer; ledger.record_action
        # kept boolean compatibility, so we need to query last reversible action if necessary.
        # For now we rely on SQLite forward entry being present; undo will query ledger for latest reversible.
        return f"Timer '{name}' started for {amount} {unit}."
