"""Onboarding Stage 2 scaffold.

Focus: connect services (calendar/music/photos).
"""

from dataclasses import dataclass


@dataclass
class OnboardingStage2:
    connected_calendar: bool = False
    connected_music: bool = False
    connected_photos: bool = False


