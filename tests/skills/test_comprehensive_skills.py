#!/usr/bin/env python3
"""Comprehensive skills test for GesahniV2."""

import asyncio
import os
import sys

# Add the app directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

# Set up minimal environment
os.environ.setdefault("HOME_ASSISTANT_URL", "http://ha")
os.environ.setdefault("HOME_ASSISTANT_TOKEN", "token")
os.environ.setdefault("OLLAMA_URL", "http://x")
os.environ.setdefault("OLLAMA_MODEL", "llama3")

import app.skills.base as base


async def test_skills_comprehensive():
    """Test multiple skills that don't require external services."""

    print("🧠 COMPREHENSIVE SKILLS TEST")
    print("=" * 50)

    test_cases = [
        ("Hello", "Smalltalk/Greeting"),
        ("What time is it?", "Clock/Time"),
        ("What is 15 + 27?", "Math"),
        ("Convert 100 feet to meters", "Unit Conversion"),
        ("Define 'serendipity'", "Dictionary"),
        ("What is the date today?", "Calendar"),
        ("What is 5 * 12?", "Math"),
        ("Convert 32°F to Celsius", "Unit Conversion"),
        ("Hi there!", "Smalltalk/Greeting"),
        ("What day is it?", "Calendar"),
    ]

    successful_tests = 0
    total_tests = len(test_cases)

    for prompt, skill_type in test_cases:
        print(f"\n🧪 Testing: {skill_type}")
        print(f"   Prompt: '{prompt}'")

        try:
            result = await base.check_builtin_skills(prompt)
            if result is not None:
                print(f"   ✅ SUCCESS: {result}")
                successful_tests += 1
            else:
                print("   ❌ NO MATCH: No skill handled this prompt")
        except Exception as e:
            print(f"   💥 ERROR: {e}")

    print("\n" + "=" * 50)
    print(f"📊 TEST RESULTS: {successful_tests}/{total_tests} skills working")
    print(f"   Success Rate: {successful_tests/total_tests:.1%}")
    if successful_tests == total_tests:
        print("🎉 ALL SKILLS WORKING! System is ready.")
    elif successful_tests >= total_tests * 0.7:
        print("✅ MOST SKILLS WORKING - System is functional.")
    else:
        print("⚠️  SOME SKILLS NOT WORKING - May need attention.")


if __name__ == "__main__":
    asyncio.run(test_skills_comprehensive())
