import inspect

from app import main


def test_no_direct_endpoints_in_main():
    """Test that no business endpoints are defined directly in main.py."""

    # Get all objects from the main module
    for name, obj in inspect.getmembers(main):
        # Skip built-in objects and the app instance itself
        if name.startswith('_') or name in ('app', 'logger', 'configure_logging'):
            continue

        # Check if object has route handler attributes
        if hasattr(obj, 'methods'):
            # This indicates a route handler function
            assert False, f"Direct route handler found in main.py: {name} = {obj}"

        # Also check for FastAPI route objects
        if hasattr(obj, 'endpoint') and hasattr(obj, 'methods'):
            assert False, f"FastAPI route object found in main.py: {name} = {obj}"


def test_no_app_decorators_in_main():
    """Alternative test: grep for @app.get/post patterns in main.py source."""

    import os
    main_file_path = os.path.join(os.path.dirname(main.__file__), 'main.py')

    with open(main_file_path) as f:
        content = f.read()

    # Look for FastAPI route decorators
    decorator_patterns = ['@app.get(', '@app.post(', '@app.put(', '@app.patch(', '@app.delete(']

    for pattern in decorator_patterns:
        if pattern in content:
            assert False, f"Direct route decorator found in main.py: {pattern}"

    # Also check for APIRouter decorators (though these should be in separate files)
    router_patterns = ['@router.get(', '@router.post(', '@router.put(', '@router.patch(', '@router.delete(']

    for pattern in router_patterns:
        if pattern in content:
            assert False, f"Router decorator found in main.py (should be in separate files): {pattern}"
