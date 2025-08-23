"""Microphone controller scaffold."""

from dataclasses import dataclass


@dataclass
class MicConfig:
    sample_rate: int = 16000
    channels: int = 1


def open_microphone(config: MicConfig) -> None:
    _ = config
    return None
