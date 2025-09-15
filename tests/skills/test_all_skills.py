#!/usr/bin/env python3
"""Run a quick verification across all registered skills and print results."""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

# Minimal env to avoid blocking external calls
os.environ.setdefault("HOME_ASSISTANT_URL", "http://localhost:8123")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://localhost:11434")

import app.skills as skills_mod
import app.skills.base as base

# Representative prompts per skill class name
SAMPLE_PROMPTS = {
    "SmalltalkSkill": "hello",
    "ClockSkill": "what time is it",
    "WorldClockSkill": "time in London",
    "WeatherSkill": "what is the weather",
    "ForecastSkill": "3 day forecast",
    "ReminderSkill": "remind me to buy milk",
    "TimerSkill": "start a countdown 10",
    "MathSkill": "what is 7 * 6",
    "UnitConversionSkill": "convert 100 feet to meters",
    "CurrencySkill": "convert 10 USD to EUR",
    "CalendarSkill": "what is the date today",
    "TeachSkill": "teach my bedroom is Hija room",
    "EntitiesSkill": "list all lights",
    "SceneSkill": "activate movie scene",
    "ScriptSkill": "run the morning script",
    "CoverSkill": "open the garage",
    "FanSkill": "turn on the fan",
    "NotifySkill": "send me a notification",
    "SearchSkill": "who is the president of the united states",
    "TranslateSkill": "translate hello to spanish",
    "NewsSkill": "top headlines",
    "JokeSkill": "tell me a joke",
    "DictionarySkill": "define serendipity",
    "RecipeSkill": "how to make pancakes",
    "LightsSkill": "turn on the living room light",
    "DoorLockSkill": "lock the front door",
    "MusicSkill": "play some music",
    "RokuSkill": "open Netflix on Roku",
    "ClimateSkill": "set thermostat to 72",
    "VacuumSkill": "start the vacuum",
    "NotesSkill": "add note buy milk",
    "StatusSkill": "what is the system status",
}


async def run_tests():
    print("Verifying registered skills...\n")
    results = []

    for skill in skills_mod.SKILLS:
        cls_name = skill.__class__.__name__
        prompt = SAMPLE_PROMPTS.get(cls_name, None)
        if prompt is None:
            # Try a generic prompt derived from the class name
            prompt = cls_name.replace("Skill", "").lower()
        try:
            resp = await base.check_builtin_skills(prompt)
            ok = resp is not None
            results.append((cls_name, ok, prompt, resp))
            status = "OK" if ok else "NO MATCH"
            print(
                f"{cls_name:25s} -> {status} | prompt: '{prompt}' | resp: {repr(resp)})"
            )
        except Exception as e:
            results.append((cls_name, False, prompt, f"ERROR: {e}"))
            print(f"{cls_name:25s} -> ERROR | prompt: '{prompt}' | {e}")

    # Summary
    succeeded = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    print("\nSummary:\n")
    print(f"  Success: {len(succeeded)}/{len(results)}")
    if failed:
        print("  Failed skills:")
        for cls, ok, prompt, resp in failed:
            print(f"    - {cls}: prompt='{prompt}' resp={repr(resp)}")


if __name__ == "__main__":
    asyncio.run(run_tests())
