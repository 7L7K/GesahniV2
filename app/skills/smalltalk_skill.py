from __future__ import annotations

import random
import re
from collections import deque
from datetime import datetime
from typing import Any, Literal, Optional

from .base import Skill

# Core phrases and tags
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

# Track used greetings and recent responses to avoid repeats
_USED_GREETINGS: set[str] = set()
_RECENT_RESPONSES: deque[str] = deque(maxlen=2)


def is_greeting(prompt: str) -> bool:
    """Return True if the prompt looks like a casual greeting."""
    p = prompt.strip().lower()
    p = re.sub(r"[!?.]+$", "", p)
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


def time_of_day() -> Literal["morning", "afternoon", "evening"]:
    now = datetime.now().hour
    if now < 12:
        return "morning"
    if now < 18:
        return "afternoon"
    return "evening"


def memory_hook(user) -> Optional[str]:
    """Return a project hook string if available."""
    return getattr(user, "last_project", None)


class SmalltalkSkill(Skill):
    """Quick canned responses for casual greetings."""

    def name(self) -> str:  # pragma: no cover - trivial
        return "smalltalk"

    def match(self, prompt: str) -> bool:
        return is_greeting(prompt)

    async def run(self, prompt: str, match: Any) -> str:
        # ``match`` is ignored; provided for compatibility with ``Skill``
        resp = self.handle(prompt, getattr(match, "user", None))
        if resp is None:
            raise ValueError("no greeting detected")
        return resp

    def handle(self, prompt: str, user=None) -> Optional[str]:
        if not is_greeting(prompt):
            return None

        greeting = self._pick_greeting()
        follow = self._follow_up(user)
        tag = self._maybe_persona_tag()

        parts = [greeting]
        if tag:
            parts.append(tag)
        parts.append(follow or FALLBACK)
        resp = " ".join(parts)

        # Avoid repeating last couple responses
        tries = 0
        while resp in _RECENT_RESPONSES and tries < 5:
            greeting = self._pick_greeting()
            tag = self._maybe_persona_tag()
            follow = self._follow_up(user)
            parts = [greeting]
            if tag:
                parts.append(tag)
            parts.append(follow or FALLBACK)
            resp = " ".join(parts)
            tries += 1
        _RECENT_RESPONSES.append(resp)
        return resp

    # Internal helpers -------------------------------------------------
    def _pick_greeting(self) -> str:
        choices = [g for g in GREETINGS if g not in _USED_GREETINGS]
        if not choices:
            _USED_GREETINGS.clear()
            choices = GREETINGS[:]
        greeting = random.choice(choices)
        _USED_GREETINGS.add(greeting)
        return greeting

    def _maybe_persona_tag(self) -> Optional[str]:
        if PERSONA_TAGS and random.random() < 0.3:
            return random.choice(PERSONA_TAGS)
        return None

    def _follow_up(self, user) -> str:
        tod = time_of_day()
        follow = {
            "morning": "Ready to crush the day?",
            "afternoon": "How’s your grind going?",
            "evening": "Late-night hustle or winding down?",
        }.get(tod, FALLBACK)
        mem = memory_hook(user)
        if mem:
            follow = f"How’s {mem} coming along?"
        return follow
