"""Built‑in skill registry for Gesahni."""

from . import base as _base
from .calendar_skill import CalendarSkill
from .checkin_skill import CheckinSkill
from .climate_skill import ClimateSkill
from .clock_skill import ClockSkill
from .cover_skill import CoverSkill
from .currency_skill import CurrencySkill
from .day_summary_skill import DaySummarySkill
from .dictionary_skill import DictionarySkill
from .door_lock_skill import DoorLockSkill
from .entities_skill import EntitiesSkill  # “list all lights”
from .fan_skill import FanSkill
from .forecast_skill import ForecastSkill
from .joke_skill import JokeSkill
from .lights_skill import LightsSkill
from .math_skill import MathSkill
from .medication_skill import MedicationSkill
from .music_skill import MusicSkill
from .news_skill import NewsSkill
from .notes_skill import NotesSkill
from .notify_skill import NotifySkill
from .recipe_skill import RecipeSkill
from .reminder_skill import ReminderSkill
from .roku_skill import RokuSkill
from .routine_skill import RoutineSkill
from .scene_skill import SceneSkill
from .script_skill import ScriptSkill
from .search_skill import SearchSkill
from .smalltalk_skill import SmalltalkSkill
from .status_skill import StatusSkill
from .suggestions_skill import SuggestionsSkill
from .teach_skill import TeachSkill  # “my bedroom is Hija room”
from .timer_skill import TimerSkill
from .translate_skill import TranslateSkill
from .undo_skill import UndoSkill
from .unit_conversion_skill import UnitConversionSkill
from .vacuum_skill import VacuumSkill
from .weather_skill import WeatherSkill
from .world_clock_skill import WorldClockSkill

try:
    from .explain_route_skill import ExplainRouteSkill  # type: ignore
except Exception:
    ExplainRouteSkill = None  # type: ignore
try:
    from .password_skill import PasswordSkill  # type: ignore
except Exception:
    PasswordSkill = None  # type: ignore
try:
    from .datetime_skill import DateTimeSkill  # type: ignore
except Exception:
    DateTimeSkill = None  # type: ignore
try:
    from .uuid_skill import UUIDSkill  # type: ignore
except Exception:
    UUIDSkill = None  # type: ignore
try:
    from .regex_skill import RegexExplainSkill  # type: ignore
except Exception:
    RegexExplainSkill = None  # type: ignore
try:
    from .text_utils_skill import TextUtilsSkill  # type: ignore
except Exception:
    TextUtilsSkill = None  # type: ignore


# Preserve class order but avoid duplicates when this module reloads
SKILL_CLASSES: list[type] = [
    # Order matters: earlier skills get first chance to match. Keep this list
    # intentionally deterministic to avoid surprises during upgrades.
    # Rationale:
    #  - SmalltalkSkill is first to quickly handle greetings and avoid heavy
    #    routing for trivial interactions.
    #  - Time/date/weather related skills run early as they are common.
    #  - Reminder/timer/notes are placed before device control so users can
    #    set things without accidental device toggles.
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
]

# Optionally include extra skills behind env flag to preserve stable ordering in tests
import os as _os

if _os.getenv("ENABLE_EXTRA_SKILLS", "0").lower() in {"1", "true", "yes"}:
    try:
        from .shopping_list_skill import ShoppingListSkill as _ShoppingListSkill

        SKILL_CLASSES.append(_ShoppingListSkill)
    except Exception:
        pass
    # Include utility/diagnostic skills behind the feature flag (only those that imported)
    for _extra in (
        ExplainRouteSkill,
        PasswordSkill,
        DateTimeSkill,
        UUIDSkill,
        RegexExplainSkill,
        TextUtilsSkill,
    ):
        if _extra is not None:
            SKILL_CLASSES.append(_extra)  # type: ignore[arg-type]

_base.SKILLS.clear()
for cls in SKILL_CLASSES:
    if not any(isinstance(s, cls) for s in _base.SKILLS):
        _base.SKILLS.append(cls())

SKILLS = _base.SKILLS

__all__ = ["SKILL_CLASSES", "SKILLS"]
