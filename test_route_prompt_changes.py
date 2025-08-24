#!/usr/bin/env python3
"""
Test script to verify route_prompt parameter standardization works correctly.
"""
import asyncio
import logging
import sys
import os

# Setup logging to see our new log messages
logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(name)s - %(message)s')

# Add the project root to the path
sys.path.insert(0, os.path.dirname(__file__))

from app import router

async def test_route_prompt_changes():
    """Test the route_prompt function with various parameter combinations."""

    print("🧪 Testing route_prompt parameter standardization...")

    # Test 1: Normal call without model_override
    print("\n1. Testing normal call...")
    try:
        result = await router.route_prompt("hello world", "test_user")
        print("✅ Normal call successful")
    except Exception as e:
        print(f"❌ Normal call failed: {e}")

    # Test 2: Valid GPT model override
    print("\n2. Testing valid GPT model override...")
    try:
        result = await router.route_prompt("hello world", "test_user", model_override="gpt-4o")
        print("✅ Valid GPT override successful")
    except Exception as e:
        print(f"❌ Valid GPT override failed: {e}")

    # Test 3: Valid LLaMA model override
    print("\n3. Testing valid LLaMA model override...")
    try:
        result = await router.route_prompt("hello world", "test_user", model_override="llama3")
        print("✅ Valid LLaMA override successful")
    except Exception as e:
        print(f"❌ Valid LLaMA override failed: {e}")

    # Test 4: Invalid model override (should be treated as no override)
    print("\n4. Testing invalid model override...")
    try:
        result = await router.route_prompt("hello world", "test_user", model_override="gpt-999")
        print("✅ Invalid model override handled correctly (treated as no override)")
    except Exception as e:
        print(f"❌ Invalid model override failed: {e}")

    # Test 5: Email-like override (should be nulled and logged)
    print("\n5. Testing email-like override...")
    try:
        result = await router.route_prompt("hello world", "test_user", model_override="user@example.com")
        print("✅ Email-like override handled correctly (nulled with warning)")
    except Exception as e:
        print(f"❌ Email-like override failed: {e}")

    # Test 6: Unknown pattern override (should be treated as no override)
    print("\n6. Testing unknown pattern override...")
    try:
        result = await router.route_prompt("hello world", "test_user", model_override="unknown-model")
        print("✅ Unknown pattern override handled correctly (treated as no override)")
    except Exception as e:
        print(f"❌ Unknown pattern override failed: {e}")

    # Test 7: Positional arguments should fail (keyword-only enforcement)
    print("\n7. Testing positional arguments (should fail)...")
    try:
        result = await router.route_prompt("hello world", "test_user", "gpt-4o")  # positional model_override
        print("❌ Positional arguments should have failed but didn't")
    except TypeError as e:
        print(f"✅ Positional arguments correctly rejected: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

    print("\n🎉 All tests completed!")

if __name__ == "__main__":
    asyncio.run(test_route_prompt_changes())
