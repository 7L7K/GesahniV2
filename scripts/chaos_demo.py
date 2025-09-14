#!/usr/bin/env python3
"""Chaos mode demonstration script.

This script demonstrates chaos mode functionality by enabling it
and making some test calls to see the chaos injection in action.

Usage:
    export CHAOS_MODE=1
    export CHAOS_SEED=42  # Optional: for reproducible chaos
    export CHAOS_VENDOR_LATENCY=0.8  # 80% chance of vendor latency
    export CHAOS_VECTOR_STORE_FAILURE=0.5  # 50% chance of vector store failure
    python scripts/chaos_demo.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.chaos import (
    is_chaos_enabled,
    log_chaos_status,
    chaos_wrap_async,
    chaos_vector_operation_sync,
)


async def demo_vendor_chaos():
    """Demo vendor chaos injection."""
    print("🔥 Testing vendor chaos injection...")

    async def mock_api_call():
        print("  📡 Making mock API call...")
        await asyncio.sleep(0.1)  # Simulate API call
        return {"status": "success", "data": "mock_response"}

    for i in range(5):
        print(f"\n  Attempt {i+1}:")
        try:
            result = await chaos_wrap_async("vendor", f"demo_call_{i}", mock_api_call)
            print(f"    ✅ Success: {result}")
        except Exception as e:
            print(f"    💥 Chaos injected: {e}")


def demo_vector_store_chaos():
    """Demo vector store chaos injection."""
    print("\n🔥 Testing vector store chaos injection...")

    def mock_vector_query():
        print("  🗃️ Making mock vector query...")
        return ["result1", "result2", "result3"]

    for i in range(5):
        print(f"\n  Attempt {i+1}:")
        try:
            result = chaos_vector_operation_sync("demo_query", mock_vector_query)
            print(f"    ✅ Success: {len(result)} results")
        except Exception as e:
            print(f"    💥 Chaos injected: {e}")


async def demo_scheduler_chaos():
    """Demo scheduler chaos injection."""
    print("\n🔥 Testing scheduler chaos injection...")

    async def mock_scheduler_task():
        print("  ⏰ Running mock scheduler task...")
        await asyncio.sleep(0.1)
        print("  ⏰ Task completed successfully")
        return "task_done"

    for i in range(3):
        print(f"\n  Attempt {i+1}:")
        try:
            from app.chaos import chaos_scheduler_operation

            result = await chaos_scheduler_operation(
                f"demo_task_{i}", mock_scheduler_task
            )
            print(f"    ✅ Success: {result}")
        except Exception as e:
            print(f"    💥 Chaos injected: {e}")


async def main():
    """Main demo function."""
    print("🎭 Chaos Mode Demonstration")
    print("=" * 50)

    if not is_chaos_enabled():
        print("❌ Chaos mode is not enabled!")
        print("To enable chaos mode, set CHAOS_MODE=1")
        print("\nExample:")
        print("  export CHAOS_MODE=1")
        print("  export CHAOS_VENDOR_LATENCY=0.8")
        print("  export CHAOS_VECTOR_STORE_FAILURE=0.5")
        print("  python scripts/chaos_demo.py")
        return

    print("✅ Chaos mode is enabled!")
    print()

    # Log chaos configuration
    log_chaos_status()

    print("\n" + "=" * 50)

    # Run demos
    await demo_vendor_chaos()
    demo_vector_store_chaos()
    await demo_scheduler_chaos()

    print("\n" + "=" * 50)
    print("🎭 Chaos demonstration complete!")
    print("\n💡 Tip: Check the logs for chaos injection events")
    print("💡 Tip: Monitor metrics at /metrics for chaos counters")


if __name__ == "__main__":
    asyncio.run(main())
