"""Smalltalk skill mini-prompt.

Respond to simple greetings with a friendly opener while keeping the chat
fresh:

- Rotate through greetings without repeating until all are used.
- Occasionally append a persona tag (configurable rate).
- Add a follow-up based on time of day or the user's last project.
- Avoid repeating the last couple of full responses.
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from .base import Skill
from .ledger import record_action

# Core phrases and tags -----------------------------------------------------
GREETINGS = [
    "Hey there!",
    "Yo!",
    "Hello!",
    "Hi!",
    "Howdy!",
    "Heyo!",
    "Ahoy!",
    "What's up?",
    "Greetings!",
    "Hiya!",
    "Salutations!",
    "Yo yo!",
    "Hey!",
    "Good to see ya!",
    "Welcome!",
    "Hey friend!",
    "Hi there!",
    "Yo, what's good?",
    "Sup!",
    "Hola!",
    "Hey, stranger!",
    "Look who it is!",
    "Hey sunshine!",
    "Howdy partner!",
    "Well hello!",
]

PERSONA_TAGS = [
    "—your code gremlin.",
    "—the ever-curious bot.",
    "—on standby and caffeinated.",
    "—spinning up brilliance.",
    "—your silent partner in crime.",
    "—with digital jazz hands.",
    "—keeping it real.",
]

FALLBACK = "Hey! I'm here—what's the move?"

log = logging.getLogger(__name__)


def _normalize(prompt: str) -> str:
    """Return a lowercase greeting without trailing punctuation."""

    p = prompt.strip().lower()
    return re.sub(r"[!?.]+$", "", p)


def is_greeting(prompt: str) -> bool:
    """Return ``True`` if *prompt* looks like a casual greeting."""

    p = _normalize(prompt)
    roots = {
        "hi",
        "hello",
        "hey",
        "yo",
        "sup",
        "good morning",
        "good afternoon",
        "good evening",
    }
    return p in roots


def memory_hook(user) -> str | None:
    """Return a formatted project hook string if available."""

    project = getattr(user, "last_project", None)
    if not project:
        return None
    project = str(project).strip()
    if not project:
        return None
    project = project.capitalize()
    return f"`{project}`"


class SmalltalkSkill(Skill):
    """Quick canned responses for casual greetings."""

    def __init__(
        self,
        *,
        time_provider: Callable[[], datetime] = datetime.now,
        persona_rate: float | None = None,
        cache_ttl: float | None = None,
    ) -> None:
        self._time_provider = time_provider
        self._persona_rate = (
            float(os.getenv("SMALLTALK_PERSONA_RATE", "0.3"))
            if persona_rate is None
            else persona_rate
        )
        self._cache_ttl = (
            float(os.getenv("SMALLTALK_CACHE_TTL", "30"))
            if cache_ttl is None
            else cache_ttl
        )
        self._used_greetings: set[str] = set()
        self._recent_responses: deque[str] = deque(maxlen=2)
        self._cache: dict[str, tuple[str, float]] = {}
        self._lock = threading.RLock()

    def name(self) -> str:  # pragma: no cover - trivial
        """Return the skill's canonical name."""

        return "smalltalk"

    def match(self, prompt: str) -> bool:
        """Return ``True`` if *prompt* is a greeting."""

        return is_greeting(prompt)

    async def run(self, prompt: str, match: Any) -> str:
        """Execute the skill and return the greeting response."""

        resp = self._respond(prompt)
        if resp is None:
            raise ValueError("no greeting detected")
        return resp

    async def handle(self, prompt: str, user=None) -> str:
        """Return a canned response or raise ``ValueError`` if not a greeting."""

        resp = self._respond(prompt, user)
        if resp is None:
            raise ValueError("no greeting detected")
        return resp

    def _respond(self, prompt: str, user=None) -> str | None:
        if not is_greeting(prompt):
            return None

        key = _normalize(prompt)
        now = time.time()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached[1] < self._cache_ttl:
                return cached[0]

            greeting = self._pick_greeting()
            follow = self._follow_up(user) or FALLBACK
            tag = self._maybe_persona_tag()

            parts = [greeting]
            if tag:
                parts.append(tag)
            parts.append(follow)
            resp = " ".join(parts)

            tries = 0
            while resp in self._recent_responses and tries < 5:
                greeting = self._pick_greeting()
                tag = self._maybe_persona_tag()
                follow = self._follow_up(user) or FALLBACK
                parts = [greeting]
                if tag:
                    parts.append(tag)
                parts.append(follow)
                resp = " ".join(parts)
                tries += 1

            self._recent_responses.append(resp)
            self._cache[key] = (resp, now)
            # record as non-reversible smalltalk for telemetry/idempotency
            idemp = f"smalltalk:{hash(resp)}:{int(time.time()//10)}"
            try:
                # best-effort ledger record
                import asyncio

                asyncio.create_task(record_action("smalltalk.respond", idempotency_key=idemp, reversible=False))
            except Exception:
                pass
            log.debug("Recorded smalltalk response", extra={"resp": resp})
            return resp

    # Internal helpers -------------------------------------------------
    def _pick_greeting(self) -> str:
        """Return a greeting not recently used."""

        with self._lock:
            choices = [g for g in GREETINGS if g not in self._used_greetings]
            if not choices:
                self._used_greetings.clear()
                choices = GREETINGS[:]
            greeting = random.choice(choices)
            self._used_greetings.add(greeting)
            log.debug("Greeting used", extra={"greeting": greeting})
            return greeting

    def _maybe_persona_tag(self) -> str | None:
        """Return a persona tag based on configured rate."""

        if PERSONA_TAGS and random.random() < self._persona_rate:
            return random.choice(PERSONA_TAGS)
        return None

    def _time_of_day(self) -> Literal["morning", "afternoon", "evening"]:
        """Return the current time of day using the injected provider."""

        hour = self._time_provider().hour
        if hour < 12:
            return "morning"
        if hour < 18:
            return "afternoon"
        return "evening"

    def _follow_up(self, user) -> str:
        """Return a follow-up question based on time of day and memory."""

        tod = self._time_of_day()
        follow = {
            "morning": "Ready to crush the day?",
            "afternoon": "How’s your grind going?",
            "evening": "Late-night hustle or winding down?",
        }.get(tod) or FALLBACK
        mem = memory_hook(user)
        if mem:
            follow = f"How’s {mem} coming along?"
        return follow or FALLBACK


__all__ = ["SmalltalkSkill", "is_greeting", "GREETINGS"]
