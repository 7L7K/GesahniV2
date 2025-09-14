"""Test feature flags behavior in different environment configurations."""

import os

import pytest


def test_feature_flags_defaults():
    """Test default feature flag values without explicit environment settings."""
    # Reset env to ensure clean state
    for key in ["GSN_ENABLE_OLLAMA", "GSN_ENABLE_HOME_ASSISTANT", "GSN_ENABLE_QDRANT"]:
        os.environ.pop(key, None)

    # Clear legacy env vars too to test pure defaults
    for key in ["OLLAMA_URL", "HOME_ASSISTANT_TOKEN", "VECTOR_STORE"]:
        os.environ.pop(key, None)

    # Import after clearing env
    from app.feature_flags import HA_ON, OLLAMA_ON, QDRANT_ON

    # All should be False by default
    assert OLLAMA_ON is False
    assert HA_ON is False
    assert QDRANT_ON is False


def test_feature_flags_explicit_enable(monkeypatch):
    """Test feature flags when explicitly enabled via GSN_ENABLE_* vars."""
    monkeypatch.setenv("GSN_ENABLE_OLLAMA", "1")
    monkeypatch.setenv("GSN_ENABLE_HOME_ASSISTANT", "true")
    monkeypatch.setenv("GSN_ENABLE_QDRANT", "yes")

    # Force reimport to pick up new env vars
    import importlib

    import app.feature_flags

    importlib.reload(app.feature_flags)

    from app.feature_flags import HA_ON, OLLAMA_ON, QDRANT_ON

    assert OLLAMA_ON is True
    assert HA_ON is True
    assert QDRANT_ON is True


def test_require_feature_dependencies():
    """Test that require_feature dependencies are callable functions."""
    # Ensure flags are off
    for key in ["GSN_ENABLE_OLLAMA", "GSN_ENABLE_HOME_ASSISTANT", "GSN_ENABLE_QDRANT"]:
        os.environ.pop(key, None)

    # Force reimport
    import importlib

    import app.feature_flags

    importlib.reload(app.feature_flags)

    from app.deps.flags import require_home_assistant, require_ollama, require_qdrant

    # Test that the dependency functions are callable
    assert callable(require_ollama)
    assert callable(require_home_assistant)
    assert callable(require_qdrant)


@pytest.mark.parametrize(
    "flag_name,expected",
    [
        ("0", False),
        ("1", True),
        ("false", False),
        ("true", True),
    ],
)
def test_is_on_helper(monkeypatch, flag_name, expected):
    """Test the _is_on helper function with various flag values."""
    from app.feature_flags import _is_on

    monkeypatch.setenv("TEST_FLAG", flag_name)
    assert _is_on("TEST_FLAG") is expected
