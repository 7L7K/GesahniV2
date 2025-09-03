#!/usr/bin/env python3
"""
Test script to verify that the get_remaining_budget fix works correctly.
"""

import asyncio
import time
import os

# Set up minimal environment
os.environ["OLLAMA_URL"] = "http://x"
os.environ["OLLAMA_MODEL"] = "llama3"
os.environ["HOME_ASSISTANT_URL"] = "http://ha"
os.environ["HOME_ASSISTANT_TOKEN"] = "token"
os.environ["ROUTER_BUDGET_MS"] = "1000"  # Short budget for testing

from app.router import get_remaining_budget


def test_get_remaining_budget():
    """Test that get_remaining_budget works correctly."""
    start_time = time.monotonic()

    # Test immediately after start
    budget = get_remaining_budget(start_time)
    print(f"Budget immediately after start: {budget:.2f} seconds")

    # Test after a short delay
    time.sleep(0.1)
    budget = get_remaining_budget(start_time)
    print(f"Budget after 0.1s delay: {budget:.2f} seconds")

    # Test after longer delay
    time.sleep(0.5)
    budget = get_remaining_budget(start_time)
    print(f"Budget after 0.6s total delay: {budget:.2f} seconds")

    print("✅ get_remaining_budget function works correctly!")


if __name__ == "__main__":
    test_get_remaining_budget()
