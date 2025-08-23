"""Tests for feature flags module."""

import os
from unittest.mock import patch

from app.feature_flags import (
    _REGISTRY,
    Flag,
    _overrides,
    clear_value,
    coerce,
    get,
    get_value,
    list_flags,
    register,
    set_value,
)


class TestFlag:
    """Test Flag dataclass."""

    def test_flag_creation(self):
        """Test creating a flag with default values."""
        flag = Flag(key="test", description="Test flag", default="0")
        assert flag.key == "test"
        assert flag.description == "Test flag"
        assert flag.default == "0"
        assert flag.type == "str"

    def test_flag_creation_with_type(self):
        """Test creating a flag with custom type."""
        flag = Flag(key="test", description="Test flag", default="1", type="bool")
        assert flag.type == "bool"

    def test_flag_env_key_property(self):
        """Test the env_key property."""
        flag = Flag(key="test_flag", description="Test flag", default="0")
        assert flag.env_key == "FLAG_TEST_FLAG"


class TestRegister:
    """Test register function."""

    def setup_method(self):
        """Clear registry before each test."""
        _REGISTRY.clear()

    def test_register_flag(self):
        """Test registering a flag."""
        register("test_flag", "Test description", "0", "bool")
        assert "test_flag" in _REGISTRY
        flag = _REGISTRY["test_flag"]
        assert flag.key == "test_flag"
        assert flag.description == "Test description"
        assert flag.default == "0"
        assert flag.type == "bool"

    def test_register_flag_default_type(self):
        """Test registering a flag with default type."""
        register("test_flag", "Test description", "default_value")
        flag = _REGISTRY["test_flag"]
        assert flag.type == "str"

    def test_register_overwrites_existing(self):
        """Test that register overwrites existing flags."""
        register("test_flag", "First description", "0")
        register("test_flag", "Second description", "1", "int")
        
        flag = _REGISTRY["test_flag"]
        assert flag.description == "Second description"
        assert flag.default == "1"
        assert flag.type == "int"


class TestCoerce:
    """Test coerce function."""

    def test_coerce_bool_true_values(self):
        """Test coercing boolean true values."""
        assert coerce("1", "bool") is True
        assert coerce("true", "bool") is True
        assert coerce("yes", "bool") is True
        assert coerce("on", "bool") is True
        assert coerce("TRUE", "bool") is True
        assert coerce("YES", "bool") is True
        assert coerce("ON", "bool") is True

    def test_coerce_bool_false_values(self):
        """Test coercing boolean false values."""
        assert coerce("0", "bool") is False
        assert coerce("false", "bool") is False
        assert coerce("no", "bool") is False
        assert coerce("off", "bool") is False
        assert coerce("anything_else", "bool") is False
        assert coerce("", "bool") is False

    def test_coerce_int(self):
        """Test coercing integer values."""
        assert coerce("123", "int") == 123
        assert coerce("0", "int") == 0
        assert coerce("-456", "int") == -456

    def test_coerce_float(self):
        """Test coercing float values."""
        assert coerce("123.45", "float") == 123.45
        assert coerce("0.0", "float") == 0.0
        assert coerce("-456.78", "float") == -456.78

    def test_coerce_str(self):
        """Test coercing string values."""
        assert coerce("hello", "str") == "hello"
        assert coerce("123", "str") == "123"
        assert coerce("", "str") == ""

    def test_coerce_unknown_type(self):
        """Test coercing unknown type returns original value."""
        assert coerce("test_value", "unknown") == "test_value"


class TestGetValue:
    """Test get_value function."""

    def setup_method(self):
        """Clear registry and overrides before each test."""
        _REGISTRY.clear()
        _overrides.clear()

    def test_get_value_with_override(self):
        """Test getting value with override set."""
        set_value("test_flag", "override_value")
        result = get_value("test_flag")
        assert result == "override_value"

    def test_get_value_registered_flag_with_env(self):
        """Test getting value for registered flag with environment variable."""
        register("test_flag", "Test flag", "default_value")
        with patch.dict(os.environ, {"FLAG_TEST_FLAG": "env_value"}):
            result = get_value("test_flag")
            assert result == "env_value"

    def test_get_value_registered_flag_without_env(self):
        """Test getting value for registered flag without environment variable."""
        register("test_flag", "Test flag", "default_value")
        with patch.dict(os.environ, {}, clear=True):
            result = get_value("test_flag")
            assert result == "default_value"

    def test_get_value_unregistered_flag(self):
        """Test getting value for unregistered flag."""
        with patch.dict(os.environ, {"FLAG_UNKNOWN": "env_value"}):
            result = get_value("unknown")
            assert result == "env_value"

    def test_get_value_unregistered_flag_no_env(self):
        """Test getting value for unregistered flag without environment variable."""
        with patch.dict(os.environ, {}, clear=True):
            result = get_value("unknown")
            assert result == ""


class TestGet:
    """Test get function."""

    def setup_method(self):
        """Clear registry and overrides before each test."""
        _REGISTRY.clear()
        _overrides.clear()

    def test_get_registered_flag_bool(self):
        """Test getting registered boolean flag."""
        register("test_flag", "Test flag", "0", "bool")
        set_value("test_flag", "1")
        result = get("test_flag")
        assert result is True

    def test_get_registered_flag_int(self):
        """Test getting registered integer flag."""
        register("test_flag", "Test flag", "0", "int")
        set_value("test_flag", "123")
        result = get("test_flag")
        assert result == 123

    def test_get_registered_flag_float(self):
        """Test getting registered float flag."""
        register("test_flag", "Test flag", "0.0", "float")
        set_value("test_flag", "123.45")
        result = get("test_flag")
        assert result == 123.45

    def test_get_registered_flag_str(self):
        """Test getting registered string flag."""
        register("test_flag", "Test flag", "default", "str")
        set_value("test_flag", "custom_value")
        result = get("test_flag")
        assert result == "custom_value"

    def test_get_unregistered_flag(self):
        """Test getting unregistered flag."""
        with patch.dict(os.environ, {"FLAG_UNKNOWN": "env_value"}):
            result = get("unknown")
            assert result == "env_value"

    def test_get_unregistered_flag_no_env(self):
        """Test getting unregistered flag without environment variable."""
        with patch.dict(os.environ, {}, clear=True):
            result = get("unknown")
            assert result == ""


class TestSetValue:
    """Test set_value function."""

    def setup_method(self):
        """Clear overrides before each test."""
        _overrides.clear()

    def test_set_value(self):
        """Test setting a value."""
        set_value("test_flag", "new_value")
        assert _overrides["test_flag"] == "new_value"

    def test_set_value_overwrites_existing(self):
        """Test that set_value overwrites existing override."""
        set_value("test_flag", "first_value")
        set_value("test_flag", "second_value")
        assert _overrides["test_flag"] == "second_value"


class TestClearValue:
    """Test clear_value function."""

    def setup_method(self):
        """Clear overrides before each test."""
        _overrides.clear()

    def test_clear_value_existing(self):
        """Test clearing an existing value."""
        set_value("test_flag", "value")
        clear_value("test_flag")
        assert "test_flag" not in _overrides

    def test_clear_value_nonexistent(self):
        """Test clearing a nonexistent value."""
        clear_value("nonexistent_flag")
        assert "nonexistent_flag" not in _overrides


class TestListFlags:
    """Test list_flags function."""

    def setup_method(self):
        """Clear registry and overrides before each test."""
        _REGISTRY.clear()
        _overrides.clear()

    def test_list_flags_empty(self):
        """Test listing flags when registry is empty."""
        result = list_flags()
        assert result == {}

    def test_list_flags_with_registered_flags(self):
        """Test listing flags with registered flags."""
        register("flag1", "First flag", "0", "bool")
        register("flag2", "Second flag", "default", "str")
        
        result = list_flags()
        
        assert "flag1" in result
        assert "flag2" in result
        assert result["flag1"]["description"] == "First flag"
        assert result["flag1"]["default"] == "0"
        assert result["flag1"]["type"] == "bool"
        assert result["flag1"]["env"] == "FLAG_FLAG1"
        assert result["flag1"]["overridden"] is False
        assert result["flag2"]["description"] == "Second flag"
        assert result["flag2"]["default"] == "default"
        assert result["flag2"]["type"] == "str"
        assert result["flag2"]["env"] == "FLAG_FLAG2"
        assert result["flag2"]["overridden"] is False

    def test_list_flags_with_overrides(self):
        """Test listing flags with overrides."""
        register("test_flag", "Test flag", "0", "bool")
        set_value("test_flag", "1")
        
        result = list_flags()
        
        assert result["test_flag"]["value"] == "1"
        assert result["test_flag"]["overridden"] is True

    def test_list_flags_with_env_values(self):
        """Test listing flags with environment values."""
        register("test_flag", "Test flag", "0", "bool")
        with patch.dict(os.environ, {"FLAG_TEST_FLAG": "1"}):
            result = list_flags()
            assert result["test_flag"]["value"] == "1"
            assert result["test_flag"]["overridden"] is False

    def test_list_flags_sorted_keys(self):
        """Test that list_flags returns sorted keys."""
        register("z_flag", "Z flag", "0")
        register("a_flag", "A flag", "0")
        register("m_flag", "M flag", "0")
        
        result = list_flags()
        keys = list(result.keys())
        assert keys == ["a_flag", "m_flag", "z_flag"]





class TestIntegration:
    """Integration tests for feature flags."""

    def setup_method(self):
        """Clear registry and overrides before each test."""
        _REGISTRY.clear()
        _overrides.clear()

    def test_flag_lifecycle(self):
        """Test complete flag lifecycle."""
        # Register flag
        register("test_flag", "Test flag", "0", "bool")
        
        # Get default value
        assert get("test_flag") is False
        
        # Set override
        set_value("test_flag", "1")
        assert get("test_flag") is True
        
        # Clear override
        clear_value("test_flag")
        assert get("test_flag") is False
        
        # Set environment variable
        with patch.dict(os.environ, {"FLAG_TEST_FLAG": "1"}):
            assert get("test_flag") is True

    def test_multiple_flags(self):
        """Test working with multiple flags."""
        register("flag1", "Flag 1", "0", "bool")
        register("flag2", "Flag 2", "100", "int")
        register("flag3", "Flag 3", "hello", "str")
        
        set_value("flag1", "1")
        set_value("flag2", "200")
        
        assert get("flag1") is True
        assert get("flag2") == 200
        assert get("flag3") == "hello"
        
        flags = list_flags()
        assert flags["flag1"]["overridden"] is True
        assert flags["flag2"]["overridden"] is True
        assert flags["flag3"]["overridden"] is False

    def test_flag_gates_combination(self):
        """Test combining multiple flags for feature gates."""
        register("feature_a", "Feature A", "0", "bool")
        register("feature_b", "Feature B", "0", "bool")
        register("feature_c", "Feature C", "0", "bool")
        
        # Enable features
        set_value("feature_a", "1")
        set_value("feature_b", "1")
        
        # Simulate feature gate logic
        def can_access_feature():
            return get("feature_a") and get("feature_b") and not get("feature_c")
        
        assert can_access_feature() is True
        
        # Disable one feature
        set_value("feature_b", "0")
        assert can_access_feature() is False
        
        # Enable all features
        set_value("feature_b", "1")
        set_value("feature_c", "1")
        assert can_access_feature() is False
