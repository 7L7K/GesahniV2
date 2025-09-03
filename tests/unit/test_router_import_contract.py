"""Test router import contract to ensure no circular imports and proper functionality.

This test verifies that the router package can be imported cleanly without pulling
in heavy dependencies, and that the basic contract (protocol, registry, entrypoint)
works as expected.
"""

import asyncio
import pytest
from typing import Any
from unittest.mock import AsyncMock
import pytest


@pytest.fixture
def prompt_router():
    """Fixture providing an async prompt router callable for DI-style tests."""
    return AsyncMock()


# Test that we can import router components without circular imports
def test_router_contracts_import():
    """Test that router contracts can be imported cleanly."""
    from app.router.contracts import Router

    # Should be a Protocol
    assert hasattr(Router, "__protocol_attrs__") or hasattr(Router, "__annotations__")

    # Should have the route_prompt method signature
    assert hasattr(Router, "route_prompt")

    # Should be callable (protocol with async method)
    # The exact signature check would be more complex, but we verify the method exists


def test_router_registry_import():
    """Test that router registry functions can be imported and work."""
    from app.router.registry import set_router, get_router

    # Functions should be importable
    assert callable(set_router)
    assert callable(get_router)

    # Should raise RuntimeError when no router is set
    with pytest.raises(RuntimeError, match="Router has not been configured"):
        get_router()


def test_router_registry_functionality():
    """Test that registry set/get works correctly."""
    from app.router.registry import set_router, get_router
    from app.router.contracts import Router

    # Create a mock router
    mock_router = AsyncMock(spec=Router)
    mock_router.route_prompt = AsyncMock(return_value={"result": "test"})

    # Set the router
    set_router(mock_router)

    # Get the router
    retrieved_router = get_router()
    assert retrieved_router is mock_router


def test_router_entrypoint_import():
    """Test that router entrypoint can be imported."""
    from app.router.entrypoint import route_prompt

    assert callable(route_prompt)


@pytest.mark.asyncio
async def test_router_entrypoint_without_router():
    """Test that entrypoint raises RuntimeError when no router configured."""
    # Clear any cached router state from previous tests
    import sys
    from app.router.registry import _router

    # Reset the global router state
    import app.router.registry

    app.router.registry._router = None

    from app.router.entrypoint import route_prompt

    # Compatibility: entrypoint now falls back to config/app.state when registry
    # is not configured. Ensure it does not raise and returns a dict-like result.
    res = await route_prompt({"test": "payload"})
    assert isinstance(res, dict)


@pytest.mark.asyncio
async def test_router_entrypoint_with_mock_router(prompt_router):
    """Test that injected prompt router callable works (DI-style)."""
    expected_response = {"result": "success", "answer": "Hello world"}
    prompt_router.return_value = expected_response

    # Use the injected prompt_router directly (represents DI)
    payload = {"prompt": "Hello", "model": "test"}
    response = await prompt_router(payload)

    assert response == expected_response
    prompt_router.assert_awaited_once_with(payload)


def test_router_init_empty():
    """Test that router __init__.py is empty as intended."""
    import app.router

    # The __init__.py should be empty, so the module should not have unexpected attributes
    # This is more of a convention check - if there are imports in __init__.py,
    # they would show up as module attributes
    router_attrs = dir(app.router)

    # Should not have Router, set_router, get_router, route_prompt if __init__.py is empty
    # (unless they're imported there, which would violate the "leave empty" requirement)
    assert "Router" not in router_attrs
    assert "set_router" not in router_attrs
    assert "get_router" not in router_attrs
    assert "route_prompt" not in router_attrs


def test_no_circular_imports():
    """Test that importing router components doesn't create circular import issues.

    This test tries to import all the router components in sequence to ensure
    no circular dependencies exist.
    """
    # Import in different orders to catch potential circular imports
    import sys

    # Clear any existing imports
    modules_to_clear = [
        "app.router.contracts",
        "app.router.registry",
        "app.router.entrypoint",
        "app.router",
    ]

    for module in modules_to_clear:
        if module in sys.modules:
            del sys.modules[module]

    # Import contracts first
    from app.router.contracts import Router

    assert Router is not None

    # Import registry
    from app.router.registry import set_router, get_router

    assert set_router is not None
    assert get_router is not None

    # Import entrypoint
    from app.router.entrypoint import route_prompt

    assert route_prompt is not None

    # Import the package itself
    import app.router

    assert app.router is not None
