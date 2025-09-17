"""Tests for secure module loader to prevent code injection attacks."""

import pytest

from app.security.module_loader import (
    SAFE_MODULES,
    SAFE_ROUTER_MODULES,
    SAFE_UTILITY_MODULES,
    _is_module_allowed,
    secure_import_attr,
    secure_import_module,
    secure_load_callable,
    secure_load_router,
)


class TestModuleAllowlist:
    """Test the allowlist validation logic."""

    def test_allowed_router_modules(self):
        """Test that valid router modules are allowed."""
        allowed_modules = [
            "app.api.auth",
            "app.router.auth_legacy_aliases",
            "app.router.google_api",
            "app.api.ask",
            "app.status",
            "app.skills.undo_skill",
            "app.auth_device",
            "app.api.auth_router_dev",
        ]

        for module in allowed_modules:
            assert _is_module_allowed(
                module, SAFE_ROUTER_MODULES
            ), f"Module {module} should be allowed"

    def test_allowed_utility_modules(self):
        """Test that valid utility modules are allowed."""
        allowed_modules = [
            "app.gpt_client",
            "app.transcription",
            "app.deps.scheduler",
            "app.router.alias_api",
        ]

        for module in allowed_modules:
            assert _is_module_allowed(
                module, SAFE_UTILITY_MODULES
            ), f"Module {module} should be allowed"

    def test_blocked_modules(self):
        """Test that dangerous modules are blocked."""
        blocked_modules = [
            "subprocess",
            "builtins",
            "importlib",
            "pickle",
            "eval",
            "exec",
            "__builtins__",
            "malicious_module",
            "random_dangerous_module",
            "socket",  # Network access
            "urllib",  # Network access
            "http",  # Network access
            "ftplib",  # Network access
            "telnetlib",  # Network access
        ]

        for module in blocked_modules:
            assert not _is_module_allowed(
                module, SAFE_MODULES
            ), f"Module {module} should be blocked"
            assert not _is_module_allowed(
                module, SAFE_ROUTER_MODULES
            ), f"Module {module} should be blocked"
            assert not _is_module_allowed(
                module, SAFE_UTILITY_MODULES
            ), f"Module {module} should be blocked"


class TestSecureImportModule:
    """Test secure module importing."""

    def test_import_allowed_module(self):
        """Test importing an allowed module."""
        # Use the logging module which should be importable
        module = secure_import_module("logging")
        assert module is not None
        assert hasattr(module, "getLogger")

    def test_import_blocked_module(self):
        """Test that importing blocked modules raises ValueError."""
        with pytest.raises(ValueError, match="not in the allowlist"):
            secure_import_module("subprocess")

        with pytest.raises(ValueError, match="not in the allowlist"):
            secure_import_module("socket")

    def test_import_nonexistent_module(self):
        """Test importing a module that doesn't exist."""
        with pytest.raises(ValueError, match="not in the allowlist"):
            secure_import_module("nonexistent.module")

    def test_import_nonexistent_allowed_module(self):
        """Test importing a non-existent but allowed module."""
        with pytest.raises(ImportError):
            secure_import_module("app.api.nonexistent")


class TestSecureImportAttr:
    """Test secure attribute importing."""

    def test_import_allowed_attr(self):
        """Test importing an allowed attribute."""
        # Import a function from an allowed module
        func = secure_import_attr("logging", "getLogger")
        assert callable(func)

    def test_import_blocked_attr(self):
        """Test that importing from blocked modules raises ValueError."""
        with pytest.raises(ValueError, match="not in the allowlist"):
            secure_import_attr("subprocess", "call")

    def test_import_nonexistent_attr(self):
        """Test importing a non-existent attribute."""
        with pytest.raises(AttributeError):
            secure_import_attr("logging", "nonexistent_function")

    def test_custom_allowlist(self):
        """Test using a custom allowlist."""
        custom_allowlist = frozenset(["subprocess"])

        # Should work with custom allowlist
        subprocess_module = secure_import_module("subprocess", custom_allowlist)
        assert subprocess_module is not None

        # Should fail with default allowlist
        with pytest.raises(ValueError, match="not in the allowlist"):
            secure_import_module("subprocess")


class TestSecureLoadRouter:
    """Test secure router loading."""

    def test_load_valid_router(self):
        """Test loading a valid router."""
        # Try to load a router from the app.api.ask module
        router = secure_load_router("app.api.ask:router")
        assert router is not None
        assert hasattr(router, "routes")  # FastAPI routers have routes attribute

    def test_load_invalid_format(self):
        """Test loading with invalid format."""
        with pytest.raises(ValueError, match="Invalid import path format"):
            secure_load_router("invalid_format")

        with pytest.raises(ValueError, match="Invalid import path format"):
            secure_load_router("module_without_colon")

    def test_load_blocked_router(self):
        """Test loading a router from blocked module."""
        with pytest.raises(ValueError, match="not in the allowlist"):
            secure_load_router("subprocess:call")


class TestSecureLoadCallable:
    """Test secure callable loading."""

    def test_load_valid_callable(self):
        """Test loading a valid callable."""
        # Try to load a utility function from logging
        callable_obj = secure_load_callable("logging:getLogger")
        assert callable(callable_obj)

    def test_load_invalid_format(self):
        """Test loading with invalid format."""
        with pytest.raises(ValueError, match="Invalid import path format"):
            secure_load_callable("invalid_format")

    def test_load_blocked_callable(self):
        """Test loading a callable from blocked module."""
        with pytest.raises(ValueError, match="not in the allowlist"):
            secure_load_callable("subprocess:call")


class TestSecurityRegression:
    """Regression tests for security issues."""

    def test_prevent_code_injection_via_path(self):
        """Test that malicious module paths cannot inject code."""
        malicious_paths = [
            "subprocess",
            "importlib",
            "builtins",
            "pickle",
            "eval",
            "exec",
            "__builtins__",
        ]

        for path in malicious_paths:
            # Test with a safe attribute name
            malicious_full_path = f"{path}:safe_attr"
            with pytest.raises(ValueError, match="not in the allowlist"):
                secure_load_router(malicious_full_path)

            with pytest.raises(ValueError, match="not in the allowlist"):
                secure_load_callable(malicious_full_path)

    def test_prevent_module_traversal(self):
        """Test that module path traversal is prevented."""
        traversal_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "app/../../../etc/shadow",
        ]

        for path in traversal_paths:
            with pytest.raises(ValueError, match="not in the allowlist"):
                secure_import_module(path)

    def test_allowlist_is_frozen(self):
        """Test that allowlists are immutable."""
        # Ensure the sets are frozenset to prevent runtime modification
        assert isinstance(SAFE_MODULES, frozenset)
        assert isinstance(SAFE_ROUTER_MODULES, frozenset)
        assert isinstance(SAFE_UTILITY_MODULES, frozenset)
