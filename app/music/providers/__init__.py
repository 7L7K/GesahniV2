"""Music provider implementations package.

Exposes base types and concrete providers when imported as a package.
"""

from .base import Device, PlaybackState, Track  # re-export for convenience

__all__ = [
    "Device",
    "PlaybackState",
    "Track",
]
