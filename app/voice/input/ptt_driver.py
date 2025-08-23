"""Push-to-Talk (PTT) button driver scaffold."""

from dataclasses import dataclass


@dataclass
class PttState:
    pressed: bool = False


def read_ptt_state() -> PttState:
    return PttState(pressed=False)
