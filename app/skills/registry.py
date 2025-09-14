from __future__ import annotations

from typing import Any

from .contracts import Skill


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: list[Skill] = []

    def register(self, skill: Skill) -> None:
        self._skills.append(skill)

    def list(self) -> list[Skill]:
        return list(self._skills)


REGISTRY = SkillRegistry()
_builtins_registered = False


def register_builtin_skills() -> None:
    global _builtins_registered
    if _builtins_registered:
        return

    # Import light, local skills and wrap to the Skill protocol
    try:
        from app.api.ask_contract import AskRequest
    except Exception:
        AskRequest = Any  # type: ignore

    # Smalltalk adaptor -------------------------------------------------
    try:
        from .smalltalk_skill import SmalltalkSkill as _Smalltalk
        from .smalltalk_skill import is_greeting as _is_greeting

        class _SmalltalkAdaptor:
            @property
            def name(self) -> str:
                return "smalltalk"

            def __init__(self) -> None:
                self._impl = _Smalltalk()

            def can_handle(self, text: str, intent_hint: str | None = None) -> bool:
                try:
                    return bool(_is_greeting(text))
                except Exception:
                    return False

            def confidence(self, text: str, intent_hint: str | None = None) -> float:
                return 0.9 if self.can_handle(text, intent_hint) else 0.0

            def cost_estimate(self, text: str) -> float:
                return 0.05

            async def run(self, request: AskRequest) -> dict[str, Any]:
                try:
                    text = await self._impl.handle(request.text)
                except Exception:
                    text = ""
                return {
                    "answer": text or "",
                    "usage": {"tokens_in": 0, "tokens_out": 0},
                    "vendor": "skill",
                    "model": self.name,
                    "cache_hit": False,
                    "observability": {
                        "route_decision": {"skill_won": self.name},
                        "cb_state": {},
                        "fallback_count": 0,
                        "hooks": {},
                        "timings": {},
                    },
                }

        REGISTRY.register(_SmalltalkAdaptor())
    except Exception:
        pass

    # Clock adaptor -----------------------------------------------------
    try:
        import re

        from .clock_skill import ClockSkill as _Clock

        class _ClockAdaptor:
            def __init__(self) -> None:
                self._impl = _Clock()
                # Access patterns from impl if available; otherwise define simple ones
                pats = getattr(_Clock, "PATTERNS", [])
                self._patterns: list[re.Pattern[str]] = list(pats)

            @property
            def name(self) -> str:
                return "clock"

            def can_handle(self, text: str, intent_hint: str | None = None) -> bool:
                t = (text or "").strip().lower()
                for p in self._patterns:
                    try:
                        if p.search(t):
                            return True
                    except Exception:
                        continue
                return False

            def confidence(self, text: str, intent_hint: str | None = None) -> float:
                return 0.8 if self.can_handle(text, intent_hint) else 0.0

            def cost_estimate(self, text: str) -> float:
                return 0.05

            async def run(self, request: AskRequest) -> dict[str, Any]:
                # Find first matching pattern and run underlying skill.run(prompt, match)

                prompt = request.text
                match = None
                for p in self._patterns:
                    m = p.search(prompt)
                    if m:
                        match = m
                        break
                text = ""
                if match is not None:
                    try:
                        text = await self._impl.run(prompt, match)  # type: ignore[arg-type]
                    except Exception:
                        text = ""
                return {
                    "answer": text or "",
                    "usage": {"tokens_in": 0, "tokens_out": 0},
                    "vendor": "skill",
                    "model": self.name,
                    "cache_hit": False,
                    "observability": {
                        "route_decision": {"skill_won": self.name},
                        "cb_state": {},
                        "fallback_count": 0,
                        "hooks": {},
                        "timings": {},
                    },
                }

        REGISTRY.register(_ClockAdaptor())
    except Exception:
        pass

    _builtins_registered = True
