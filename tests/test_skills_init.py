import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import skills
from app.skills.calendar_skill import CalendarSkill
from app.skills.climate_skill import ClimateSkill
from app.skills.clock_skill import ClockSkill
from app.skills.cover_skill import CoverSkill
from app.skills.currency_skill import CurrencySkill
from app.skills.dictionary_skill import DictionarySkill
from app.skills.door_lock_skill import DoorLockSkill
from app.skills.entities_skill import EntitiesSkill
from app.skills.fan_skill import FanSkill
from app.skills.forecast_skill import ForecastSkill
from app.skills.joke_skill import JokeSkill
from app.skills.lights_skill import LightsSkill
from app.skills.math_skill import MathSkill
from app.skills.music_skill import MusicSkill
from app.skills.news_skill import NewsSkill
from app.skills.notes_skill import NotesSkill
from app.skills.notify_skill import NotifySkill
from app.skills.recipe_skill import RecipeSkill
from app.skills.reminder_skill import ReminderSkill
from app.skills.roku_skill import RokuSkill
from app.skills.scene_skill import SceneSkill
from app.skills.script_skill import ScriptSkill
from app.skills.search_skill import SearchSkill
from app.skills.smalltalk_skill import SmalltalkSkill
from app.skills.status_skill import StatusSkill
from app.skills.teach_skill import TeachSkill
from app.skills.timer_skill import TimerSkill
from app.skills.translate_skill import TranslateSkill
from app.skills.unit_conversion_skill import UnitConversionSkill
from app.skills.vacuum_skill import VacuumSkill
from app.skills.weather_skill import WeatherSkill
from app.skills.world_clock_skill import WorldClockSkill

EXPECTED_ORDER = [
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


def test_skills_order_and_length():
    assert skills.SKILL_CLASSES == EXPECTED_ORDER
    assert len(skills.SKILL_CLASSES) == len(skills.SKILLS)
    for skill_obj, cls in zip(skills.SKILLS, EXPECTED_ORDER, strict=False):
        assert isinstance(skill_obj, cls)
