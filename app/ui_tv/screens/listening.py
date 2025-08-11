"""Listening screen scaffold for the TV UI.

Represents Push-to-Talk or wake-word active state, with live captions.
"""

from dataclasses import dataclass


@dataclass
class ListeningScreenModel:
    is_ptt_active: bool
    partial_transcript: str | None = None


def new_listening_state() -> ListeningScreenModel:
    return ListeningScreenModel(is_ptt_active=False, partial_transcript=None)


