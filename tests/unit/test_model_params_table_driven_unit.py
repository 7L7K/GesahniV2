from typing import Any

import pytest

from app import model_params as mp


class TestBaseDefaults:
    """Table-driven tests for base_defaults() function."""
    
    @pytest.mark.parametrize("env_vars,expected", [
        # Default values when no env vars set
        ({}, {
            "temperature": 0.1,
            "top_p": 0.9,
            "max_tokens": None,
            "stop": None,
            "max_completion_tokens": None,
        }),
        
        # Temperature variations
        ({"GEN_TEMPERATURE": "0.0"}, {"temperature": 0.0}),
        ({"GEN_TEMPERATURE": "0.5"}, {"temperature": 0.5}),
        ({"GEN_TEMPERATURE": "1.0"}, {"temperature": 1.0}),
        ({"GEN_TEMPERATURE": "2.0"}, {"temperature": 2.0}),
        
        # Top_p variations
        ({"GEN_TOP_P": "0.1"}, {"top_p": 0.1}),
        ({"GEN_TOP_P": "0.5"}, {"top_p": 0.5}),
        ({"GEN_TOP_P": "1.0"}, {"top_p": 1.0}),
        
        # Max tokens variations
        ({"GEN_MAX_TOKENS": "100"}, {"max_tokens": 100}),
        ({"GEN_MAX_TOKENS": "1000"}, {"max_tokens": 1000}),
        ({"GEN_MAX_TOKENS": "0"}, {"max_tokens": 0}),
        
        # Max completion tokens variations
        ({"GEN_MAX_COMPLETION_TOKENS": "50"}, {"max_completion_tokens": 50}),
        ({"GEN_MAX_COMPLETION_TOKENS": "500"}, {"max_completion_tokens": 500}),
        
        # Stop sequences
        ({"GEN_STOP": "END"}, {"stop": ["END"]}),
        ({"GEN_STOP": "a,b,c"}, {"stop": ["a", "b", "c"]}),
        ({"GEN_STOP": "a\nb\nc"}, {"stop": ["a", "b", "c"]}),
        ({"GEN_STOP": "a, b , c"}, {"stop": ["a", "b", "c"]}),
        ({"GEN_STOP": ""}, {"stop": None}),
        ({"GEN_STOP": "   "}, {"stop": None}),
        
        # Combined scenarios
        ({"GEN_TEMPERATURE": "0.3", "GEN_TOP_P": "0.7", "GEN_MAX_TOKENS": "200"}, {
            "temperature": 0.3,
            "top_p": 0.7,
            "max_tokens": 200,
        }),
    ])
    def test_base_defaults_env_variations(self, monkeypatch, env_vars: dict[str, str], expected: dict[str, Any]):
        """Test base_defaults with various environment variable combinations."""
        # Clear all relevant env vars first
        for key in ["GEN_TEMPERATURE", "GEN_TOP_P", "GEN_MAX_TOKENS", "GEN_MAX_COMPLETION_TOKENS", "GEN_STOP"]:
            monkeypatch.delenv(key, raising=False)
        
        # Set the test env vars
        for key, value in env_vars.items():
            monkeypatch.setenv(key, value)
        
        result = mp.base_defaults()
        
        # Check only the expected keys
        for key, expected_value in expected.items():
            assert result[key] == expected_value, f"Expected {key}={expected_value}, got {result[key]}"
    
    @pytest.mark.parametrize("env_var,invalid_value,expected_default", [
        ("GEN_TEMPERATURE", "not_a_number", 0.1),
        ("GEN_TEMPERATURE", "", 0.1),
        ("GEN_TOP_P", "invalid", 0.9),
        ("GEN_MAX_TOKENS", "abc", None),  # max_tokens defaults to None
        ("GEN_MAX_COMPLETION_TOKENS", "xyz", None),  # max_completion_tokens defaults to None
    ])
    def test_base_defaults_invalid_values(self, monkeypatch, env_var: str, invalid_value: str, expected_default: Any):
        """Test that invalid environment values fall back to defaults."""
        monkeypatch.setenv(env_var, invalid_value)
        
        # For max_tokens and max_completion_tokens, invalid values should raise ValueError
        if env_var in ["GEN_MAX_TOKENS", "GEN_MAX_COMPLETION_TOKENS"]:
            with pytest.raises(ValueError):
                mp.base_defaults()
        else:
            result = mp.base_defaults()
            if env_var == "GEN_TEMPERATURE":
                assert result["temperature"] == expected_default
            elif env_var == "GEN_TOP_P":
                assert result["top_p"] == expected_default


class TestMergeParams:
    """Table-driven tests for merge_params() function."""
    
    @pytest.mark.parametrize("overrides,expected_changes", [
        # No overrides
        (None, {}),
        ({}, {}),
        
        # Basic parameter overrides
        ({"temperature": 0.5}, {"temperature": 0.5}),
        ({"top_p": 0.8}, {"top_p": 0.8}),
        ({"max_tokens": 100}, {"max_tokens": 100}),
        
        # Stop sequence normalization
        ({"stop": "END"}, {"stop": ["END"]}),
        ({"stop": ["a", "b"]}, {"stop": ["a", "b"]}),
        ({"stop": ("a", "b")}, {"stop": ["a", "b"]}),
        ({"stop": {"a", "b"}}, {"stop": ["a", "b"]}),  # Set gets converted to list
        ({"stop": ["a", "", "b"]}, {"stop": ["a", "b"]}),  # Empty strings filtered
        ({"stop": [1, "b", 3]}, {"stop": ["1", "b", "3"]}),  # Numbers converted to strings
        
        # None values are ignored
        ({"temperature": None}, {}),
        ({"top_p": None, "max_tokens": 100}, {"max_tokens": 100}),
        ({"stop": None}, {}),
        
        # Additional provider-specific keys
        ({"foo": "bar"}, {"foo": "bar"}),
        ({"custom_param": 123}, {"custom_param": 123}),
        
        # Complex combinations
        ({"temperature": 0.3, "stop": ["a", "b"], "custom": "value"}, {
            "temperature": 0.3,
            "stop": ["a", "b"],
            "custom": "value"
        }),
    ])
    def test_merge_params_variations(self, monkeypatch, overrides: dict[str, Any] | None, expected_changes: dict[str, Any]):
        """Test merge_params with various override combinations."""
        # Set up base environment
        monkeypatch.setenv("GEN_TEMPERATURE", "0.1")
        monkeypatch.setenv("GEN_TOP_P", "0.9")
        
        result = mp.merge_params(overrides)
        
        # Check that base defaults are preserved (unless overridden)
        if "temperature" not in expected_changes:
            assert result["temperature"] == 0.1
        if "top_p" not in expected_changes:
            assert result["top_p"] == 0.9
        
        # Check the expected changes
        for key, expected_value in expected_changes.items():
            if key == "stop" and isinstance(expected_value, list):
                # For stop sequences, check that they're properly normalized
                # For sets, order doesn't matter
                if isinstance(overrides.get("stop"), set):
                    assert sorted(result[key]) == sorted(expected_value)
                else:
                    assert result[key] == expected_value
            else:
                assert result[key] == expected_value
    
    @pytest.mark.parametrize("stop_input,expected_output", [
        # String inputs
        ("END", ["END"]),
        ("a,b,c", ["a,b,c"]),  # String is treated as single item
        ("a, b , c", ["a, b , c"]),  # String is treated as single item
        ("", [""]),  # Empty string becomes single empty item
        ("   ", ["   "]),  # Whitespace is preserved
        
        # List inputs
        (["a", "b"], ["a", "b"]),
        (["a", "", "b"], ["a", "b"]),  # Empty strings filtered
        ([1, "b", 3], ["1", "b", "3"]),  # Numbers converted to strings
        
        # Tuple inputs
        (("a", "b"), ["a", "b"]),
        (("a", "", "b"), ["a", "b"]),
        
        # Set inputs
        ({"a", "b"}, ["a", "b"]),  # Order may vary
        ({"a", "", "b"}, ["a", "b"]),
        
        # Invalid types (should be ignored)
        (123, None),
        (None, None),
        (True, None),
    ])
    def test_merge_params_stop_normalization(self, monkeypatch, stop_input: Any, expected_output: list[str] | None):
        """Test stop sequence normalization in merge_params."""
        monkeypatch.setenv("GEN_TEMPERATURE", "0.1")
        
        result = mp.merge_params({"stop": stop_input})
        
        # The actual behavior: strings are treated as single items, not split
        if expected_output is None:
            assert result["stop"] is None
        else:
            # For set inputs, order doesn't matter
            if isinstance(stop_input, set):
                assert sorted(result["stop"]) == sorted(expected_output)
            else:
                assert result["stop"] == expected_output


class TestForOpenAI:
    """Table-driven tests for for_openai() function."""
    
    @pytest.mark.parametrize("overrides,expected_openai_args", [
        # Basic mapping
        (None, {"temperature": 0.1, "top_p": 0.9}),
        ({}, {"temperature": 0.1, "top_p": 0.9}),
        
        # Parameter overrides
        ({"temperature": 0.5}, {"temperature": 0.5, "top_p": 0.9}),
        ({"top_p": 0.8}, {"temperature": 0.1, "top_p": 0.8}),
        
        # Max tokens mapping (legacy to modern)
        ({"max_tokens": 100}, {"temperature": 0.1, "top_p": 0.9, "max_completion_tokens": 100}),
        ({"max_completion_tokens": 200}, {"temperature": 0.1, "top_p": 0.9, "max_completion_tokens": 200}),
        
        # Precedence: max_completion_tokens over max_tokens
        ({"max_tokens": 100, "max_completion_tokens": 200}, {
            "temperature": 0.1, "top_p": 0.9, "max_completion_tokens": 200
        }),
        
        # Stop sequences
        ({"stop": ["END"]}, {"temperature": 0.1, "top_p": 0.9, "stop": ["END"]}),
        ({"stop": "END"}, {"temperature": 0.1, "top_p": 0.9, "stop": ["END"]}),
        
        # Additional keys are dropped
        ({"foo": "bar"}, {"temperature": 0.1, "top_p": 0.9}),
        ({"num_predict": 100}, {"temperature": 0.1, "top_p": 0.9}),
        
        # None values are ignored, so base defaults remain
        ({"temperature": None}, {"temperature": 0.1, "top_p": 0.9}),
        ({"top_p": None}, {"temperature": 0.1, "top_p": 0.9}),
        ({"stop": None}, {"temperature": 0.1, "top_p": 0.9}),
        
        # Complex combinations
        ({"temperature": 0.3, "max_tokens": 150, "stop": ["a", "b"]}, {
            "temperature": 0.3, "top_p": 0.9, "max_completion_tokens": 150, "stop": ["a", "b"]
        }),
    ])
    def test_for_openai_mapping(self, monkeypatch, overrides: dict[str, Any] | None, expected_openai_args: dict[str, Any]):
        """Test OpenAI parameter mapping."""
        # Set up base environment
        monkeypatch.setenv("GEN_TEMPERATURE", "0.1")
        monkeypatch.setenv("GEN_TOP_P", "0.9")
        
        result = mp.for_openai(overrides)
        
        # Check that only expected keys are present
        assert set(result.keys()) == set(expected_openai_args.keys())
        
        # Check each expected value
        for key, expected_value in expected_openai_args.items():
            assert result[key] == expected_value
    
    def test_for_openai_never_includes_max_tokens(self, monkeypatch):
        """Test that OpenAI mapping never includes the legacy 'max_tokens' parameter."""
        monkeypatch.setenv("GEN_MAX_TOKENS", "100")
        
        result = mp.for_openai()
        
        assert "max_tokens" not in result
        assert "max_completion_tokens" in result


class TestForOllama:
    """Table-driven tests for for_ollama() function."""
    
    @pytest.mark.parametrize("overrides,expected_ollama_args", [
        # Basic mapping
        (None, {"temperature": 0.1, "top_p": 0.9}),
        ({}, {"temperature": 0.1, "top_p": 0.9}),
        
        # Parameter overrides
        ({"temperature": 0.5}, {"temperature": 0.5, "top_p": 0.9}),
        ({"top_p": 0.8}, {"temperature": 0.1, "top_p": 0.8}),
        
        # Max tokens mapping (max_tokens -> num_predict)
        ({"max_tokens": 100}, {"temperature": 0.1, "top_p": 0.9, "num_predict": 100}),
        ({"max_tokens": 0}, {"temperature": 0.1, "top_p": 0.9, "num_predict": 0}),
        
        # Stop sequences
        ({"stop": ["END"]}, {"temperature": 0.1, "top_p": 0.9, "stop": ["END"]}),
        ({"stop": "END"}, {"temperature": 0.1, "top_p": 0.9, "stop": ["END"]}),
        
        # Additional Ollama-specific options are preserved
        ({"num_ctx": 2048}, {"temperature": 0.1, "top_p": 0.9, "num_ctx": 2048}),
        ({"repeat_penalty": 1.1}, {"temperature": 0.1, "top_p": 0.9, "repeat_penalty": 1.1}),
        ({"seed": 42}, {"temperature": 0.1, "top_p": 0.9, "seed": 42}),
        
        # Complex combinations
        ({"temperature": 0.3, "max_tokens": 150, "num_ctx": 4096, "stop": ["a", "b"]}, {
            "temperature": 0.3, "top_p": 0.9, "num_predict": 150, "num_ctx": 4096, "stop": ["a", "b"]
        }),
        
        # None values are ignored, so base defaults remain
        ({"temperature": None}, {"temperature": 0.1, "top_p": 0.9}),
        ({"top_p": None}, {"temperature": 0.1, "top_p": 0.9}),
        ({"max_tokens": None}, {"temperature": 0.1, "top_p": 0.9}),
        ({"stop": None}, {"temperature": 0.1, "top_p": 0.9}),
    ])
    def test_for_ollama_mapping(self, monkeypatch, overrides: dict[str, Any] | None, expected_ollama_args: dict[str, Any]):
        """Test Ollama parameter mapping."""
        # Set up base environment
        monkeypatch.setenv("GEN_TEMPERATURE", "0.1")
        monkeypatch.setenv("GEN_TOP_P", "0.9")
        
        result = mp.for_ollama(overrides)
        
        # Check that only expected keys are present
        assert set(result.keys()) == set(expected_ollama_args.keys())
        
        # Check each expected value
        for key, expected_value in expected_ollama_args.items():
            assert result[key] == expected_value
    
    def test_for_ollama_preserves_additional_options(self, monkeypatch):
        """Test that Ollama mapping preserves additional provider-specific options."""
        monkeypatch.setenv("GEN_TEMPERATURE", "0.1")
        
        overrides = {
            "num_ctx": 2048,
            "repeat_penalty": 1.1,
            "seed": 42,
            "custom_option": "value"
        }
        
        result = mp.for_ollama(overrides)
        
        # Check that all additional options are preserved
        for key, value in overrides.items():
            assert result[key] == value


class TestEdgeCases:
    """Edge case tests for model_params functions."""
    
    def test_env_float_edge_cases(self, monkeypatch):
        """Test _env_float with edge cases."""
        # Test with very large numbers
        monkeypatch.setenv("GEN_TEMPERATURE", "1e10")
        result = mp.base_defaults()
        assert result["temperature"] == 1e10
        
        # Test with negative numbers
        monkeypatch.setenv("GEN_TEMPERATURE", "-0.5")
        result = mp.base_defaults()
        assert result["temperature"] == -0.5
        
        # Test with zero
        monkeypatch.setenv("GEN_TEMPERATURE", "0")
        result = mp.base_defaults()
        assert result["temperature"] == 0.0
    
    def test_env_int_edge_cases(self, monkeypatch):
        """Test _env_int with edge cases."""
        # Test with large numbers
        monkeypatch.setenv("GEN_MAX_TOKENS", "999999")
        result = mp.base_defaults()
        assert result["max_tokens"] == 999999
        
        # Test with zero
        monkeypatch.setenv("GEN_MAX_TOKENS", "0")
        result = mp.base_defaults()
        assert result["max_tokens"] == 0
        
        # Test with negative numbers
        monkeypatch.setenv("GEN_MAX_TOKENS", "-100")
        result = mp.base_defaults()
        assert result["max_tokens"] == -100
    
    def test_env_list_edge_cases(self, monkeypatch):
        """Test _env_list with edge cases."""
        # Test with single item
        monkeypatch.setenv("GEN_STOP", "END")
        result = mp.base_defaults()
        assert result["stop"] == ["END"]
        
        # Test with mixed whitespace
        monkeypatch.setenv("GEN_STOP", "  a  ,  b  ,  c  ")
        result = mp.base_defaults()
        assert result["stop"] == ["a", "b", "c"]
        
        # Test with empty items
        monkeypatch.setenv("GEN_STOP", "a,,b,,c")
        result = mp.base_defaults()
        assert result["stop"] == ["a", "b", "c"]
        
        # Test with only empty items
        monkeypatch.setenv("GEN_STOP", ",,,")
        result = mp.base_defaults()
        assert result["stop"] == []  # Empty list, not None
    
    def test_merge_params_with_empty_iterables(self, monkeypatch):
        """Test merge_params with empty iterables."""
        monkeypatch.setenv("GEN_TEMPERATURE", "0.1")
        
        # Empty list
        result = mp.merge_params({"stop": []})
        assert result["stop"] == []  # Empty list, not None
        
        # Empty tuple
        result = mp.merge_params({"stop": ()})
        assert result["stop"] == []  # Empty list, not None
        
        # Empty set
        result = mp.merge_params({"stop": set()})
        assert result["stop"] == []  # Empty list, not None
    
    def test_provider_mapping_with_none_values(self, monkeypatch):
        """Test that None values are properly handled in provider mappings."""
        monkeypatch.setenv("GEN_TEMPERATURE", "0.1")
        monkeypatch.setenv("GEN_TOP_P", "0.9")
        
        # Test OpenAI mapping - None values are ignored, so base defaults remain
        openai_result = mp.for_openai({
            "temperature": None,
            "top_p": None,
            "max_tokens": None,
            "stop": None
        })
        assert openai_result == {"temperature": 0.1, "top_p": 0.9}
        
        # Test Ollama mapping - None values are ignored, so base defaults remain
        ollama_result = mp.for_ollama({
            "temperature": None,
            "top_p": None,
            "max_tokens": None,
            "stop": None
        })
        assert ollama_result == {"temperature": 0.1, "top_p": 0.9}
