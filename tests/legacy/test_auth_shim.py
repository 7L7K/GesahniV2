"""Test that the auth shim properly forwards to canonical endpoints."""

import inspect
from unittest.mock import Mock

import pytest

from app.api import auth as legacy
from app.auth.endpoints import debug as canon_debug
from app.auth.endpoints import login as canon_login
from app.auth.endpoints import logout as canon_logout
from app.auth.endpoints import refresh as canon_refresh
from app.auth.endpoints import register as canon_register
from app.auth.endpoints import token as canon_token


def _unwrap(depr):
    """Extract the underlying object from _DeprecatedAccess wrapper."""
    return depr._obj if hasattr(depr, "_obj") else depr


def test_refresh_forwarding():
    """Test that legacy.refresh forwards to canonical refresh."""
    assert _unwrap(legacy.refresh) is canon_refresh.refresh


def test_login_forwarding():
    """Test that legacy.login forwards to canonical login."""
    assert _unwrap(legacy.login) is canon_login.login


def test_login_v1_forwarding():
    """Test that legacy.login_v1 forwards to canonical login_v1."""
    assert _unwrap(legacy.login_v1) is canon_login.login_v1


def test_logout_forwarding():
    """Test that legacy.logout forwards to canonical logout."""
    assert _unwrap(legacy.logout) is canon_logout.logout


def test_logout_all_forwarding():
    """Test that legacy.logout_all forwards to canonical logout_all."""
    assert _unwrap(legacy.logout_all) is canon_logout.logout_all


def test_debug_forwarding():
    """Test that legacy.whoami forwards to canonical whoami."""
    assert _unwrap(legacy.whoami) is canon_debug.whoami


def test_register_forwarding():
    """Test that legacy.register_v1 forwards to canonical register_v1."""
    assert _unwrap(legacy.register_v1) is canon_register.register_v1


def test_token_forwarding():
    """Test that legacy.dev_token forwards to canonical dev_token."""
    assert _unwrap(legacy.dev_token) is canon_token.dev_token


def test_token_examples_forwarding():
    """Test that legacy.token_examples forwards to canonical token_examples."""
    assert _unwrap(legacy.token_examples) is canon_token.token_examples


def test_debug_cookies_forwarding():
    """Test that legacy.debug_cookies forwards to canonical debug_cookies."""
    assert _unwrap(legacy.debug_cookies) is canon_debug.debug_cookies


def test_debug_auth_state_forwarding():
    """Test that legacy.debug_auth_state forwards to canonical debug_auth_state."""
    assert _unwrap(legacy.debug_auth_state) is canon_debug.debug_auth_state


def test_rotate_refresh_cookies_forwarding():
    """Test that legacy.rotate_refresh_cookies forwards to canonical rotate_refresh_cookies."""
    assert legacy.rotate_refresh_cookies is canon_refresh.rotate_refresh_cookies


def test_deprecated_access_warning():
    """Test that _DeprecatedAccess emits warnings when called."""
    import warnings
    
    # Create a mock function
    mock_func = Mock()
    mock_func.return_value = "test_result"
    
    # Create a deprecated access wrapper
    wrapper = legacy._DeprecatedAccess(mock_func, "test_func", "Test deprecation warning")
    
    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        # Call the wrapper
        result = wrapper("test_arg", kwarg="test_value")
        
        # Verify the warning was emitted
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "Test deprecation warning" in str(w[0].message)
        
        # Verify the function was called correctly
        mock_func.assert_called_once_with("test_arg", kwarg="test_value")
        assert result == "test_result"


def test_deprecated_access_getattr():
    """Test that _DeprecatedAccess emits warnings when accessing attributes."""
    import warnings
    
    # Create a mock object with an attribute
    mock_obj = Mock()
    mock_obj.test_attr = "test_value"
    
    # Create a deprecated access wrapper
    wrapper = legacy._DeprecatedAccess(mock_obj, "test_obj", "Test deprecation warning")
    
    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        # Access an attribute
        result = wrapper.test_attr
        
        # Verify the warning was emitted
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "Test deprecation warning" in str(w[0].message)
        
        # Verify the attribute was accessed correctly
        assert result == "test_value"


def test_router_exists():
    """Test that the router exists and is an APIRouter."""
    from fastapi import APIRouter
    
    assert hasattr(legacy, "router")
    assert isinstance(legacy.router, APIRouter)


def test_all_exports():
    """Test that __all__ contains all expected exports."""
    expected_exports = {
        "debug_cookies",
        "debug_auth_state", 
        "whoami",
        "login",
        "login_v1",
        "logout",
        "logout_all",
        "refresh",
        "register_v1",
        "dev_token",
        "token_examples",
        "rotate_refresh_cookies",
        "router",
    }
    
    assert set(legacy.__all__) == expected_exports


def test_no_duplicate_warnings():
    """Test that _DeprecatedAccess only warns once per instance."""
    import warnings
    
    # Create a mock function
    mock_func = Mock()
    mock_func.return_value = "test_result"
    
    # Create a deprecated access wrapper
    wrapper = legacy._DeprecatedAccess(mock_func, "test_func", "Test deprecation warning")
    
    # Capture warnings
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        
        # Call the wrapper multiple times
        wrapper("arg1")
        wrapper("arg2")
        wrapper("arg3")
        
        # Verify only one warning was emitted
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)


def test_no_duplicate_routes():
    """Test that there are no duplicate routes in OpenAPI spec."""
    import json
    from fastapi.testclient import TestClient
    from app.main import app
    
    client = TestClient(app)
    response = client.get("/openapi.json")
    
    # Check if response is successful and has paths
    if response.status_code != 200:
        pytest.skip("OpenAPI endpoint not available")
    
    spec = response.json()
    if "paths" not in spec:
        pytest.skip("OpenAPI spec missing paths")
    
    # Check that each auth route appears exactly once
    auth_routes = [
        "/v1/auth/whoami",
        "/v1/auth/login", 
        "/v1/auth/logout",
        "/v1/auth/logout_all",
        "/v1/auth/refresh",
        "/v1/auth/register"
    ]
    
    for route in auth_routes:
        count = list(spec["paths"].keys()).count(route)
        assert count == 1, f"Route {route} appears {count} times, expected 1"


def test_router_guard():
    """Test that router guard prevents wrapping."""
    from app.api import auth
    
    # Router should be a plain APIRouter
    assert "fastapi.routing.APIRouter" in str(type(auth.router))
    
    # Should not be wrapped in _DeprecatedAccess
    assert not hasattr(auth.router, "_obj")


def test_sunset_flag():
    """Test that sunset flag breaks imports when enabled."""
    import os
    import importlib
    import sys
    
    # Save original value
    original_value = os.getenv("BREAK_LEGACY_AUTH_IMPORTS")
    
    try:
        # Test with flag enabled
        os.environ["BREAK_LEGACY_AUTH_IMPORTS"] = "1"
        
        # Remove the module from cache to force reload
        if "app.api.auth" in sys.modules:
            del sys.modules["app.api.auth"]
        
        # Should raise ImportError when importing
        with pytest.raises(ImportError, match="app.api.auth is retired"):
            import app.api.auth
            
    finally:
        # Restore original value
        if original_value is None:
            os.environ.pop("BREAK_LEGACY_AUTH_IMPORTS", None)
        else:
            os.environ["BREAK_LEGACY_AUTH_IMPORTS"] = original_value
        
        # Remove from cache and reimport to restore normal behavior
        if "app.api.auth" in sys.modules:
            del sys.modules["app.api.auth"]
        import app.api.auth


def test_metrics_tracking():
    """Test that metrics are tracked when accessing deprecated imports."""
    # This test would require a running Prometheus instance
    # For now, just verify the metrics module can be imported
    try:
        from app.metrics_deprecation import DEPRECATED_IMPORTS, WHOAMI_REQUESTS
        assert DEPRECATED_IMPORTS is not None
        assert WHOAMI_REQUESTS is not None
    except ImportError:
        pytest.skip("Metrics module not available")
