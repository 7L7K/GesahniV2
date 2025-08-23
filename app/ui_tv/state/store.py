"""Minimal UI state model shared with the TV UI.

This exists to document/coordinate state managed on the frontend (Next.js) and
signals emitted by the voice pipeline.
"""

from dataclasses import dataclass


@dataclass
class UiState:
    voice_active: bool
    onboarding_stage: int
    consent_microphone: bool | None
    consent_calendar: bool | None
    do_not_disturb_window: tuple[int, int] | None


def default_ui_state() -> UiState:
    return UiState(
        voice_active=False,
        onboarding_stage=0,
        consent_microphone=None,
        consent_calendar=None,
        do_not_disturb_window=None,
    )
