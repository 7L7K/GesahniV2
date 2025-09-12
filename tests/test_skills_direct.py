#!/usr/bin/env python3
"""Test script to verify skills are working directly."""

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


async def test_skills():
    """Test if skills are working."""
    print("Testing skills directly...")

    # Test greeting
    result = await base.check_builtin_skills("hello")
    print(f"Greeting test result: {result}")

    # Test weather
    result = await base.check_builtin_skills("what is the weather")
    print(f"Weather test result: {result}")

    # Test math
    result = await base.check_builtin_skills("what is 2 + 2")
    print(f"Math test result: {result}")

    # Test time
    result = await base.check_builtin_skills("what time is it")
    print(f"Time test result: {result}")


if __name__ == "__main__":
    asyncio.run(test_skills())
