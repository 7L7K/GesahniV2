"""Built‑in skill registry for Gesahni."""

from .base import SKILLS

# core skills
from .clock_skill import ClockSkill
from .weather_skill import WeatherSkill
from .reminder_skill import ReminderSkill
from .calendar_skill import CalendarSkill
from .alarm_skill import AlarmSkill
from .timer_skill import TimerSkill
from .math_skill import MathSkill
from .flashcard_skill import FlashcardSkill
from .lights_skill import LightsSkill
from .door_lock_skill import DoorLockSkill
from .music_skill import MusicSkill
from .roku_skill import RokuSkill
from .climate_skill import ClimateSkill
from .vacuum_skill import VacuumSkill
from .notes_skill import NotesSkill
from .status_skill import StatusSkill
from .scene_skill import SceneSkill
from .script_skill import ScriptSkill
from .cover_skill import CoverSkill
from .fan_skill import FanSkill
from .notify_skill import NotifySkill
from .search_skill import SearchSkill
from .translate_skill import TranslateSkill

# NEW skills
from .teach_skill import TeachSkill          # “my bedroom is Hija room”
from .entities_skill import EntitiesSkill    # “list all lights”

# ───────────────────────────────────────────
# Instantiate in desired order
# ───────────────────────────────────────────
SKILLS.extend([
    ClockSkill(),
    WeatherSkill(),
    ReminderSkill(),
    CalendarSkill(),
    AlarmSkill(),
    TimerSkill(),
    MathSkill(),
    FlashcardSkill(),

    TeachSkill(),        # alias learning first for quick matches
    EntitiesSkill(),     # optional helper to dump HA entities

    SceneSkill(),
    ScriptSkill(),
    CoverSkill(),
    FanSkill(),
    NotifySkill(),
    SearchSkill(),
    TranslateSkill(),

    LightsSkill(),
    DoorLockSkill(),
    MusicSkill(),
    RokuSkill(),
    ClimateSkill(),
    VacuumSkill(),
    NotesSkill(),
    StatusSkill(),
])

# ───────────────────────────────────────────
# Public exports
# ───────────────────────────────────────────
__all__ = [
    "ClockSkill",
    "WeatherSkill",
    "ReminderSkill",
    "CalendarSkill",
    "AlarmSkill",
    "TimerSkill",
    "MathSkill",
    "FlashcardSkill",
    "TeachSkill",
    "EntitiesSkill",
    "SceneSkill",
    "ScriptSkill",
    "CoverSkill",
    "FanSkill",
    "NotifySkill",
    "SearchSkill",
    "TranslateSkill",
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
