import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")
from app import skills

EXPECTED_ORDER = [
    skills.ClockSkill,
    skills.WorldClockSkill,
    skills.WeatherSkill,
    skills.ForecastSkill,
    skills.ReminderSkill,
    skills.TimerSkill,
    skills.MathSkill,
    skills.UnitConversionSkill,
    skills.CurrencySkill,
    skills.CalendarSkill,
    skills.TeachSkill,
    skills.EntitiesSkill,
    skills.SceneSkill,
    skills.ScriptSkill,
    skills.CoverSkill,
    skills.FanSkill,
    skills.NotifySkill,
    skills.SearchSkill,
    skills.TranslateSkill,
    skills.NewsSkill,
    skills.JokeSkill,
    skills.DictionarySkill,
    skills.RecipeSkill,
    skills.LightsSkill,
    skills.DoorLockSkill,
    skills.MusicSkill,
    skills.RokuSkill,
    skills.ClimateSkill,
    skills.VacuumSkill,
    skills.NotesSkill,
    skills.StatusSkill,
]


def test_skills_order_and_length():
    assert len(skills.SKILLS) == len(EXPECTED_ORDER)
    for skill_obj, cls in zip(skills.SKILLS, EXPECTED_ORDER):
        assert isinstance(skill_obj, cls)
