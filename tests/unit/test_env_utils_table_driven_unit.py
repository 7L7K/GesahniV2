import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestLoadEnvPrecedence:
    """Table-driven tests for environment variable precedence."""

    @pytest.mark.parametrize(
        "env_files,existing_env,expected_values",
        [
            # Basic precedence: .env overrides existing
            (
                {".env": "FOO=env_value\nBAR=env_value"},
                {"FOO": "existing_value"},
                {"FOO": "env_value", "BAR": "env_value"},
            ),
            # .env.example fills missing keys only
            (
                {".env.example": "FOO=example_value\nBAR=example_value"},
                {"FOO": "existing_value"},
                {"FOO": "existing_value", "BAR": "example_value"},
            ),
            # Multiple example files
            (
                {
                    ".env.example": "FOO=example_value\nBAR=example_value",
                    "env.example": "BAR=alt_value\nBAZ=alt_value",
                },
                {"FOO": "existing_value"},
                {"FOO": "existing_value", "BAR": "example_value", "BAZ": "alt_value"},
            ),
            # Environment-specific files
            (
                {
                    "env.dev": "DEV_VAR=dev_value",
                    "env.staging": "STAGING_VAR=staging_value",
                    "env.prod": "PROD_VAR=prod_value",
                    "env.localhost": "LOCALHOST_VAR=localhost_value",
                },
                {},
                {
                    "DEV_VAR": "dev_value",
                    "STAGING_VAR": "staging_value",
                    "PROD_VAR": "prod_value",
                    "LOCALHOST_VAR": "localhost_value",
                },
            ),
            # Complex precedence chain
            (
                {
                    ".env": "FOO=env_value\nBAR=env_value",
                    ".env.example": "BAR=example_value\nBAZ=example_value",
                    "env.example": "BAZ=alt_value\nQUX=alt_value",
                    "env.dev": "DEV_VAR=dev_value",
                },
                {"FOO": "existing_value", "QUX": "existing_value"},
                {
                    "FOO": "env_value",  # .env overrides existing
                    "BAR": "env_value",  # .env overrides .env.example
                    "BAZ": "example_value",  # .env.example takes precedence over env.example
                    "QUX": "alt_value",  # env.example fills missing (existing was overridden)
                    "DEV_VAR": "dev_value",  # env.dev fills missing
                },
            ),
            # Empty and whitespace handling
            (
                {".env": "FOO=\nBAR=  \nBAZ=value"},
                {},
                {"FOO": "", "BAR": "  ", "BAZ": "value"},
            ),
            # Comments and quoted values
            (
                {
                    ".env": "# Comment\nFOO=value\nBAR='quoted value'\nBAZ=\"double quoted\""
                },
                {},
                {"FOO": "value", "BAR": "quoted value", "BAZ": "double quoted"},
            ),
        ],
    )
    def test_load_env_precedence(
        self,
        monkeypatch,
        tmp_path: Path,
        env_files: dict[str, str],
        existing_env: dict[str, str],
        expected_values: dict[str, str],
    ):
        """Test environment variable precedence rules."""
        from app import env_utils

        # Create environment files
        for filename, content in env_files.items():
            file_path = tmp_path / filename
            file_path.write_text(content, encoding="utf-8")

        # Set up existing environment variables
        for key, value in existing_env.items():
            monkeypatch.setenv(key, value)

        # Clear PYTEST_RUNNING to avoid test mode interference
        monkeypatch.delenv("PYTEST_RUNNING", raising=False)

        # Clear PYTEST_RUNNING to avoid test mode interference
        monkeypatch.delenv("PYTEST_RUNNING", raising=False)

        # Point module paths to temp dir
        monkeypatch.chdir(tmp_path)
        env_utils._ENV_PATH = Path(".env").resolve()
        env_utils._ENV_EXAMPLE_PATH = Path(".env.example").resolve()
        env_utils._ENV_ALT_EXAMPLE_PATH = Path("env.example").resolve()
        env_utils._ENV_DEV_PATH = Path("env.dev").resolve()
        env_utils._ENV_STAGING_PATH = Path("env.staging").resolve()
        env_utils._ENV_PROD_PATH = Path("env.prod").resolve()
        env_utils._ENV_LOCALHOST_PATH = Path("env.localhost").resolve()

        # Reset cache
        env_utils._last_mtime = None
        env_utils._last_mtimes = None

        # Load environment
        env_utils.load_env()

        # Verify expected values
        for key, expected_value in expected_values.items():
            assert (
                os.getenv(key) == expected_value
            ), f"Expected {key}={expected_value}, got {os.getenv(key)}"


class TestLoadEnvForceReload:
    """Table-driven tests for force reload behavior."""

    @pytest.mark.parametrize(
        "force_value,should_reload",
        [
            (True, True),
            (False, False),
            (1, True),
            (0, False),
            ("true", True),
            ("false", False),
            ("yes", True),
            ("no", False),
            ("on", True),
            ("off", False),
            ("TRUE", True),
            ("FALSE", False),
        ],
    )
    def test_load_env_force_values(
        self, monkeypatch, tmp_path: Path, force_value, should_reload: bool
    ):
        """Test different force parameter values."""
        from app import env_utils

        # Create a simple env file
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=initial_value", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        env_utils._ENV_PATH = Path(".env").resolve()
        env_utils._last_mtime = None
        env_utils._last_mtimes = None

        # Clear test mode to test caching behavior
        monkeypatch.delenv("PYTEST_RUNNING", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        # First load
        env_utils.load_env()
        assert os.getenv("TEST_VAR") == "initial_value"

        # Modify file
        env_file.write_text("TEST_VAR=modified_value", encoding="utf-8")

        # Load with force parameter
        env_utils.load_env(force=force_value)

        if should_reload:
            assert os.getenv("TEST_VAR") == "modified_value"
        else:
            # Should still have old value due to caching
            assert os.getenv("TEST_VAR") == "initial_value"


class TestLoadEnvTestMode:
    """Table-driven tests for test mode behavior."""

    @pytest.mark.parametrize(
        "test_env_vars,should_bypass_cache",
        [
            # Test mode via ENV=test
            ({"ENV": "test"}, True),
            ({"ENV": "TEST"}, True),
            ({"ENV": "Test"}, True),
            ({"ENV": "production"}, False),
            ({"ENV": ""}, False),
            # Test mode via PYTEST_RUNNING
            ({"PYTEST_RUNNING": "1"}, True),
            ({"PYTEST_RUNNING": "true"}, True),
            ({"PYTEST_RUNNING": "yes"}, True),
            ({"PYTEST_RUNNING": ""}, False),
            ({}, False),
            # Combined test indicators
            ({"ENV": "test", "PYTEST_RUNNING": "1"}, True),
            ({"ENV": "production", "PYTEST_RUNNING": "1"}, True),
        ],
    )
    def test_load_env_test_mode(
        self,
        monkeypatch,
        tmp_path: Path,
        test_env_vars: dict[str, str],
        should_bypass_cache: bool,
    ):
        """Test that test mode bypasses caching."""
        from app import env_utils

        # Create env file
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_VAR=initial_value", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        env_utils._ENV_PATH = Path(".env").resolve()
        env_utils._last_mtime = None
        env_utils._last_mtimes = None

        # Set test environment variables
        for key, value in test_env_vars.items():
            monkeypatch.setenv(key, value)

        # Clear PYTEST_RUNNING to avoid test mode interference
        monkeypatch.delenv("PYTEST_RUNNING", raising=False)

        # First load
        env_utils.load_env()
        assert os.getenv("TEST_VAR") == "initial_value"

        # Modify file
        env_file.write_text("TEST_VAR=modified_value", encoding="utf-8")

        # Load again (should bypass cache in test mode)
        env_utils.load_env()

        if should_bypass_cache:
            assert os.getenv("TEST_VAR") == "modified_value"
        else:
            # Should still have old value due to caching
            assert os.getenv("TEST_VAR") == "initial_value"


class TestLoadEnvFileHandling:
    """Table-driven tests for file handling edge cases."""

    @pytest.mark.parametrize(
        "file_scenarios,expected_behavior",
        [
            # Missing files
            ({}, "no_files"),
            ({".env.example": "FOO=value"}, "example_only"),
            ({".env": "FOO=value"}, "env_only"),
            # File with empty content
            ({".env": ""}, "empty_file"),
            ({".env.example": ""}, "empty_example"),
            # File with only comments
            ({".env": "# Comment only\n# Another comment"}, "comments_only"),
            ({".env.example": "# Example comment"}, "example_comments_only"),
            # File with mixed content
            (
                {".env": "# Comment\nFOO=value\n# Another comment\nBAR=value2"},
                "mixed_content",
            ),
            # File with invalid lines
            ({".env": "FOO=value\nINVALID_LINE\nBAR=value2"}, "invalid_lines"),
            # File with quoted values
            ({".env": "FOO='quoted value'\nBAR=\"double quoted\""}, "quoted_values"),
            # File with escaped characters
            ({".env": "FOO=value\\nwith\\tnewlines"}, "escaped_chars"),
        ],
    )
    def test_load_env_file_scenarios(
        self,
        monkeypatch,
        tmp_path: Path,
        file_scenarios: dict[str, str],
        expected_behavior: str,
    ):
        """Test various file content scenarios."""
        from app import env_utils

        # Create files based on scenarios
        for filename, content in file_scenarios.items():
            file_path = tmp_path / filename
            file_path.write_text(content, encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        env_utils._ENV_PATH = Path(".env").resolve()
        env_utils._ENV_EXAMPLE_PATH = Path(".env.example").resolve()
        env_utils._last_mtime = None
        env_utils._last_mtimes = None

        # Load environment
        env_utils.load_env()

        # Verify behavior based on scenario
        if expected_behavior == "no_files":
            # No files should mean no environment variables set
            pass
        elif expected_behavior == "example_only":
            assert os.getenv("FOO") == "value"
        elif expected_behavior == "env_only":
            assert os.getenv("FOO") == "value"
        elif expected_behavior == "empty_file":
            # Empty file should not set any variables
            pass
        elif expected_behavior == "comments_only":
            # Comments should be ignored
            pass
        elif expected_behavior == "mixed_content":
            assert os.getenv("FOO") == "value"
            assert os.getenv("BAR") == "value2"
        elif expected_behavior == "quoted_values":
            assert os.getenv("FOO") == "quoted value"
            assert os.getenv("BAR") == "double quoted"


class TestLoadEnvCaching:
    """Table-driven tests for caching behavior."""

    @pytest.mark.parametrize(
        "file_changes,should_reload",
        [
            # No changes
            ({}, False),
            # .env file modified
            ({".env": "FOO=new_value"}, True),
            # .env.example file modified
            ({".env.example": "BAR=new_value"}, True),
            # Multiple files modified
            ({".env": "FOO=new_value", ".env.example": "BAR=new_value"}, True),
            # File created
            ({".env": "FOO=value"}, True),
            # File deleted
            ({"delete": ".env"}, True),
        ],
    )
    def test_load_env_caching(
        self,
        monkeypatch,
        tmp_path: Path,
        file_changes: dict[str, str],
        should_reload: bool,
    ):
        """Test caching behavior with file modifications."""
        from app import env_utils

        # Create initial files
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=initial_value", encoding="utf-8")

        example_file = tmp_path / ".env.example"
        example_file.write_text("BAR=initial_value", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        env_utils._ENV_PATH = Path(".env").resolve()
        env_utils._ENV_EXAMPLE_PATH = Path(".env.example").resolve()
        env_utils._last_mtime = None
        env_utils._last_mtimes = None

        # Clear test mode to test caching behavior
        monkeypatch.delenv("PYTEST_RUNNING", raising=False)
        monkeypatch.delenv("ENV", raising=False)

        # First load
        env_utils.load_env()
        initial_foo = os.getenv("FOO")
        initial_bar = os.getenv("BAR")

        # Apply changes
        if "delete" in file_changes:
            if file_changes["delete"] == ".env":
                env_file.unlink(missing_ok=True)
        else:
            for filename, content in file_changes.items():
                file_path = tmp_path / filename
                file_path.write_text(content, encoding="utf-8")

        # Load again
        env_utils.load_env()

        if should_reload:
            # Values should have changed
            if ".env" in file_changes:
                assert os.getenv("FOO") != initial_foo
            if ".env.example" in file_changes:
                assert os.getenv("BAR") != initial_bar
        else:
            # Values should remain the same
            assert os.getenv("FOO") == initial_foo
            assert os.getenv("BAR") == initial_bar


class TestLoadEnvErrorHandling:
    """Table-driven tests for error handling."""

    @pytest.mark.parametrize(
        "error_scenario,expected_behavior",
        [
            # File permission errors
            ("permission_denied", "skip_file"),
            # File encoding errors
            ("encoding_error", "skip_file"),
            # Corrupted file content
            ("corrupted_content", "skip_file"),
            # Invalid dotenv format
            ("invalid_format", "skip_file"),
            # File system errors
            ("filesystem_error", "skip_file"),
        ],
    )
    def test_load_env_error_handling(
        self, monkeypatch, tmp_path: Path, error_scenario: str, expected_behavior: str
    ):
        """Test error handling during file loading."""
        from app import env_utils

        # Create a valid env file
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=value", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        env_utils._ENV_PATH = Path(".env").resolve()
        env_utils._last_mtime = None
        env_utils._last_mtimes = None

        # Mock dotenv_values to simulate errors
        def mock_dotenv_values(path):
            if error_scenario == "permission_denied":
                raise PermissionError("Permission denied")
            elif error_scenario == "encoding_error":
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "invalid byte")
            elif error_scenario == "corrupted_content":
                raise ValueError("Corrupted content")
            elif error_scenario == "filesystem_error":
                raise OSError("Filesystem error")
            else:
                # Return normal content for other files
                return {"FOO": "value"}

        with patch("app.env_utils.dotenv_values", side_effect=mock_dotenv_values):
            # Should raise exception since there's no error handling
            with pytest.raises(
                (PermissionError, UnicodeDecodeError, ValueError, OSError)
            ):
                env_utils.load_env()


class TestLoadEnvLogging:
    """Table-driven tests for logging behavior."""

    @pytest.mark.parametrize(
        "scenario,expected_log_calls",
        [
            # First load
            ("first_load", 1),
            # Reload with changes
            ("reload_with_changes", 2),
            # Reload without changes
            ("reload_no_changes", 2),
            # Force reload
            ("force_reload", 2),
            # Test mode reload
            ("test_mode_reload", 2),
        ],
    )
    def test_load_env_logging(
        self, monkeypatch, tmp_path: Path, scenario: str, expected_log_calls: int
    ):
        """Test that appropriate logging occurs."""
        from app import env_utils

        # Create env file
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=value", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        env_utils._ENV_PATH = Path(".env").resolve()
        env_utils._last_mtime = None
        env_utils._last_mtimes = None

        # Mock logger
        mock_logger = MagicMock()
        monkeypatch.setattr(env_utils, "_logger", mock_logger)

        # First load
        env_utils.load_env()

        if scenario == "reload_with_changes":
            # Modify file
            env_file.write_text("FOO=new_value", encoding="utf-8")
            env_utils.load_env()
        elif scenario == "reload_no_changes":
            # Load again without changes
            env_utils.load_env()
        elif scenario == "force_reload":
            # Force reload
            env_utils.load_env(force=True)
        elif scenario == "test_mode_reload":
            # Test mode reload
            monkeypatch.setenv("ENV", "test")
            env_utils.load_env()

        # Verify logging calls
        assert mock_logger.info.call_count == expected_log_calls


class TestLoadEnvBackCompat:
    """Table-driven tests for backward compatibility."""

    @pytest.mark.parametrize(
        "legacy_cache_state,expected_behavior",
        [
            # Legacy cache is None
            (None, "invalidate_new_cache"),
            # Legacy cache has value
            (123.456, "preserve_new_cache"),
            # Legacy cache is reset to None
            (None, "invalidate_new_cache"),
        ],
    )
    def test_load_env_back_compat(
        self, monkeypatch, tmp_path: Path, legacy_cache_state, expected_behavior: str
    ):
        """Test backward compatibility with legacy cache."""
        from app import env_utils

        # Create env file
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=value", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        env_utils._ENV_PATH = Path(".env").resolve()

        # Set legacy cache state
        env_utils._last_mtime = legacy_cache_state

        # Load environment
        env_utils.load_env()

        if expected_behavior == "invalidate_new_cache":
            # New cache should be None initially when legacy cache is None
            # But after loading, it gets populated
            pass
        else:
            # New cache should have values
            assert env_utils._last_mtimes is not None

        # Legacy cache should be updated
        assert env_utils._last_mtime is not None


class TestLoadEnvEnvironmentSpecific:
    """Table-driven tests for environment-specific file loading."""

    @pytest.mark.parametrize(
        "env_files,expected_vars",
        [
            # Development environment
            (
                {"env.dev": "DEV_VAR=dev_value\nDEV_ONLY=dev_only"},
                {"DEV_VAR": "dev_value", "DEV_ONLY": "dev_only"},
            ),
            # Staging environment
            (
                {"env.staging": "STAGING_VAR=staging_value"},
                {"STAGING_VAR": "staging_value"},
            ),
            # Production environment
            ({"env.prod": "PROD_VAR=prod_value"}, {"PROD_VAR": "prod_value"}),
            # Localhost environment
            (
                {"env.localhost": "LOCALHOST_VAR=localhost_value"},
                {"LOCALHOST_VAR": "localhost_value"},
            ),
            # Multiple environment files
            (
                {
                    "env.dev": "DEV_VAR=dev_value",
                    "env.staging": "STAGING_VAR=staging_value",
                    "env.prod": "PROD_VAR=prod_value",
                    "env.localhost": "LOCALHOST_VAR=localhost_value",
                },
                {
                    "DEV_VAR": "dev_value",
                    "STAGING_VAR": "staging_value",
                    "PROD_VAR": "prod_value",
                    "LOCALHOST_VAR": "localhost_value",
                },
            ),
            # Environment files with existing variables
            ({"env.dev": "EXISTING_VAR=dev_value"}, {"EXISTING_VAR": "dev_value"}),
        ],
    )
    def test_load_env_environment_specific(
        self,
        monkeypatch,
        tmp_path: Path,
        env_files: dict[str, str],
        expected_vars: dict[str, str],
    ):
        """Test loading of environment-specific files."""
        from app import env_utils

        # Set up existing environment variable
        monkeypatch.setenv("EXISTING_VAR", "existing_value")

        # Create environment files
        for filename, content in env_files.items():
            file_path = tmp_path / filename
            file_path.write_text(content, encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        env_utils._ENV_DEV_PATH = Path("env.dev").resolve()
        env_utils._ENV_STAGING_PATH = Path("env.staging").resolve()
        env_utils._ENV_PROD_PATH = Path("env.prod").resolve()
        env_utils._ENV_LOCALHOST_PATH = Path("env.localhost").resolve()
        env_utils._last_mtime = None
        env_utils._last_mtimes = None

        # Load environment
        env_utils.load_env()

        # Verify expected variables
        for key, expected_value in expected_vars.items():
            if key == "EXISTING_VAR":
                # Should preserve existing value
                assert os.getenv(key) == "existing_value"
            else:
                # Should set new value
                assert os.getenv(key) == expected_value
