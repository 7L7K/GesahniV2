"""Built in skill registry."""

from .base import SKILLS
from .clock_skill import ClockSkill
from .weather_skill import WeatherSkill
from .reminder_skill import ReminderSkill
from .lights_skill import LightsSkill
from .door_lock_skill import DoorLockSkill
from .music_skill import MusicSkill
from .roku_skill import RokuSkill
from .climate_skill import ClimateSkill
from .vacuum_skill import VacuumSkill
from .notes_skill import NotesSkill
from .status_skill import StatusSkill

# Instantiate in desired order
SKILLS.extend([
    ClockSkill(),
    WeatherSkill(),
    ReminderSkill(),
    LightsSkill(),
    DoorLockSkill(),
    MusicSkill(),
    RokuSkill(),
    ClimateSkill(),
    VacuumSkill(),
    NotesSkill(),
    StatusSkill(),
])

__all__ = [
    "ClockSkill",
    "WeatherSkill",
    "ReminderSkill",
    "LightsSkill",
    "DoorLockSkill",
    "MusicSkill",
    "RokuSkill",
    "ClimateSkill",
    "VacuumSkill",
    "NotesSkill",
    "StatusSkill",
    "SKILLS",
]
