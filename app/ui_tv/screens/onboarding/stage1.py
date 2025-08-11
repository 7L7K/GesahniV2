"""Onboarding Stage 1 scaffold.

Focus: initial consent and safety checks.
"""

from dataclasses import dataclass


@dataclass
class OnboardingStage1:
    consent_microphone: bool | None = None
    consent_calendar: bool | None = None


