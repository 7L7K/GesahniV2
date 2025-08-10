"""Built‑in skill registry for Gesahni."""

from . import base as _base
from .smalltalk_skill import SmalltalkSkill
from .clock_skill import ClockSkill
from .world_clock_skill import WorldClockSkill
from .weather_skill import WeatherSkill
from .forecast_skill import ForecastSkill
from .reminder_skill import ReminderSkill
from .timer_skill import TimerSkill
from .math_skill import MathSkill
from .unit_conversion_skill import UnitConversionSkill
from .currency_skill import CurrencySkill
from .calendar_skill import CalendarSkill
from .teach_skill import TeachSkill  # “my bedroom is Hija room”
from .entities_skill import EntitiesSkill  # “list all lights”
from .scene_skill import SceneSkill
from .script_skill import ScriptSkill
from .cover_skill import CoverSkill
from .fan_skill import FanSkill
from .notify_skill import NotifySkill
from .search_skill import SearchSkill
from .translate_skill import TranslateSkill
from .news_skill import NewsSkill
from .joke_skill import JokeSkill
from .dictionary_skill import DictionarySkill
from .recipe_skill import RecipeSkill
from .lights_skill import LightsSkill
from .door_lock_skill import DoorLockSkill
from .music_skill import MusicSkill
from .roku_skill import RokuSkill
from .climate_skill import ClimateSkill
from .vacuum_skill import VacuumSkill
from .notes_skill import NotesSkill
from .status_skill import StatusSkill
from .sports_skill import SportsSkill

# Preserve class order but avoid duplicates when this module reloads
SKILL_CLASSES: list[type] = [
    SmalltalkSkill,
    ClockSkill,
    WorldClockSkill,
    WeatherSkill,
    ForecastSkill,
    ReminderSkill,
    TimerSkill,
    MathSkill,
    UnitConversionSkill,
    CurrencySkill,
    CalendarSkill,
    TeachSkill,
    EntitiesSkill,
    SceneSkill,
    ScriptSkill,
    CoverSkill,
    FanSkill,
    NotifySkill,
    SearchSkill,
    TranslateSkill,
    NewsSkill,
    JokeSkill,
    DictionarySkill,
    RecipeSkill,
    LightsSkill,
    DoorLockSkill,
    MusicSkill,
    RokuSkill,
    ClimateSkill,
    VacuumSkill,
    NotesSkill,
    StatusSkill,
    SportsSkill,
]

_base.SKILLS.clear()
for cls in SKILL_CLASSES:
    if not any(isinstance(s, cls) for s in _base.SKILLS):
        _base.SKILLS.append(cls())

SKILLS = _base.SKILLS

__all__ = ["SKILL_CLASSES", "SKILLS"]
