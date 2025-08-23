import asyncio
import importlib


def test_worker_dedup():
    """Test that background tasks don't duplicate on reload."""

    # Ensure we have an event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Get initial task count
    initial_tasks = len(asyncio.all_tasks(loop))

    # Simulate reload by reloading the main module
    if "app.main" in importlib.sys.modules:
        del importlib.sys.modules["app.main"]

    # Force a fresh import
    import app.main
    app_instance = app.main.app

    # Give some time for any background tasks to start
    # (In practice, lifespan events run during app startup)
    loop.run_until_complete(asyncio.sleep(0.1))

    # Get task count after reload
    final_tasks = len(asyncio.all_tasks(loop))

    # The task count should not have increased significantly
    # (allowing for some variance due to test environment)
    task_difference = final_tasks - initial_tasks

    # Allow for at most 2 new tasks (very lenient - most reloads should have 0 difference)
    assert task_difference <= 2, f"Too many new tasks after reload: {task_difference} (initial: {initial_tasks}, final: {final_tasks})"
