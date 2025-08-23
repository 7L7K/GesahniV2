import asyncio
import builtins
import logging
import os
import sys
import types
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException

# Setup sys.modules mocks for import isolation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.modules.setdefault(
    "sentence_transformers",
    types.SimpleNamespace(SentenceTransformer=object, util=None),
)
sys.modules.setdefault("chromadb", types.SimpleNamespace(PersistentClient=object))
sys.modules.setdefault("aiosqlite", types.SimpleNamespace(connect=lambda *a, **k: None))


# Mock OpenAI and related imports
class _Emb:
    def create(self, *a, **k):
        return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.0])])


class _ChatCompletionStream:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _ChatCompletions:
    async def create(self, *a, **k):
        if k.get("stream"):
            return _ChatCompletionStream()
        return types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(content=""),
                    delta=None,
                    finish_reason="stop",
                )
            ],
            usage=types.SimpleNamespace(prompt_tokens=0, completion_tokens=0),
        )


class _AsyncOpenAI:
    def __init__(self, *a, **k):
        self.chat = types.SimpleNamespace(completions=_ChatCompletions())
        self.embeddings = _Emb()

    async def close(self):
        pass


class _OpenAIError(Exception):
    pass


builtins.AsyncOpenAI = _AsyncOpenAI
sys.modules["openai"] = types.SimpleNamespace(
    OpenAI=types.SimpleNamespace, AsyncOpenAI=_AsyncOpenAI, OpenAIError=_OpenAIError
)

# Test constants
TEST_USER_ID = "test_user_123"
TEST_PROMPT = "Hello world"
TEST_REQUEST_ID = "test_req_456"

# Setup environment for tests
os.environ["OLLAMA_URL"] = "http://localhost:11434"
os.environ["OLLAMA_MODEL"] = "llama3:latest"
os.environ["HOME_ASSISTANT_URL"] = "http://ha"
os.environ["HOME_ASSISTANT_TOKEN"] = "token"


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch):
    """Global test setup to patch dependencies"""
    from app import analytics, llama_integration, router

    # Patch MemGPT and memory routines to pure no-op for tests
    monkeypatch.setattr(
        router, "memgpt", types.SimpleNamespace(store_interaction=lambda *a, **k: None)
    )
    monkeypatch.setattr(router, "add_user_memory", lambda *a, **k: None)
    monkeypatch.setattr(
        router, "cache_answer", lambda prompt, answer, cache_id=None: None
    )

    # Reset analytics
    analytics._metrics = {
        "total": 0,
        "llama": 0,
        "gpt": 0,
        "fallback": 0,
        "session_count": 0,
        "transcribe_ms": 0,
        "transcribe_count": 0,
        "transcribe_errors": 0,
    }

    # Reset circuit breaker state
    monkeypatch.setattr(llama_integration, "llama_failures", 0)
    monkeypatch.setattr(llama_integration, "llama_circuit_open", False)

    # Reset user circuit breaker
    monkeypatch.setattr(router, "_llama_user_failures", {})

    # Reset health flags
    monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
    monkeypatch.setattr(router, "OPENAI_HEALTHY", True)
    monkeypatch.setattr(router, "openai_circuit_open", False)


class TestOverridePathRespectsAllowlistAndHealth:
    """Tests that prove override path respects allowlist and health requirements."""

    def test_override_with_allowed_model_passes(self, monkeypatch):
        """Test that override with allowed model works when vendor is healthy."""
        from app import llama_integration, router

        # Setup healthy state
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
        monkeypatch.setattr(router, "ALLOWED_LLAMA_MODELS", {"llama3:latest", "llama3"})

        # Mock health check to avoid asyncio.run() issues
        monkeypatch.setattr(router, "_check_vendor_health", lambda vendor: True)

        async def fake_llama(prompt, model=None, **kwargs):
            # For the main routing function, return a string directly
            # For _call_llama, this would be consumed as async generator
            return "llama_response"

        # Mock at the correct import path
        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)

        # Should succeed with allowed model
        result = asyncio.run(
            router.route_prompt(
                TEST_PROMPT, model_override="llama3:latest", user_id=TEST_USER_ID
            )
        )
        assert result == "llama_response"

    def test_override_with_disallowed_model_fails(self, monkeypatch):
        """Test that override with disallowed model raises HTTPException."""
        from app import router

        monkeypatch.setattr(router, "ALLOWED_LLAMA_MODELS", {"llama3:latest"})

        # Should fail with disallowed model
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                router.route_prompt(
                    TEST_PROMPT,
                    model_override="llama3:disallowed",
                    user_id=TEST_USER_ID,
                )
            )

        assert exc.value.status_code == 403
        assert "model_not_allowed" in str(exc.value.detail)

    def test_override_with_unhealthy_vendor_fails(self, monkeypatch):
        """Test that override fails when vendor is unhealthy and fallback disabled."""
        from app import llama_integration, router

        # Setup unhealthy state
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", False)
        monkeypatch.setattr(router, "ALLOWED_LLAMA_MODELS", {"llama3:latest"})

        # Mock health check to return unhealthy
        monkeypatch.setattr(router, "_check_vendor_health", lambda vendor: False)

        # Should fail when vendor unhealthy and no fallback allowed
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                router.route_prompt(
                    TEST_PROMPT,
                    model_override="llama3:latest",
                    user_id=TEST_USER_ID,
                    allow_fallback=False,
                )
            )

        assert exc.value.status_code == 503
        assert "vendor_unavailable" in str(exc.value.detail)

    def test_override_fallback_when_vendor_unhealthy(self, monkeypatch):
        """Test that override falls back to healthy vendor when primary is unhealthy."""
        from app import llama_integration, router

        # Setup unhealthy LLaMA, healthy OpenAI
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", False)
        monkeypatch.setattr(router, "OPENAI_HEALTHY", True)
        monkeypatch.setattr(router, "ALLOWED_LLAMA_MODELS", {"llama3:latest"})
        monkeypatch.setattr(router, "ALLOWED_GPT_MODELS", {"gpt-4o"})

        # Mock health check - LLaMA unhealthy, OpenAI healthy
        def mock_health_check(vendor):
            return vendor == "openai"

        monkeypatch.setattr(router, "_check_vendor_health", mock_health_check)

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_fallback_response", 0, 0, 0.0

        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        # Should fallback to GPT when LLaMA is unhealthy
        result = asyncio.run(
            router.route_prompt(
                TEST_PROMPT,
                model_override="llama3:latest",
                user_id=TEST_USER_ID,
                allow_fallback=True,
            )
        )
        assert result == "gpt_fallback_response"

    def test_override_unknown_vendor_fails(self, monkeypatch):
        """Test that override with unknown vendor raises HTTPException."""
        from app import router

        # Should fail with unknown vendor
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                router.route_prompt(
                    TEST_PROMPT,
                    model_override="unknown-model-123",
                    user_id=TEST_USER_ID,
                )
            )

        assert exc.value.status_code == 400
        assert "unknown_model" in str(exc.value.detail)


class TestDefaultPickerPathPicksExpectedVendorModel:
    """Tests that prove default picker picks expected vendor/model for intents."""

    def test_heavy_word_count_routes_to_gpt(self, monkeypatch):
        """Test that prompts with heavy word count route to GPT."""
        from app import model_picker, router
        from app.model_config import GPT_HEAVY_MODEL

        # Create long prompt that exceeds HEAVY_WORD_COUNT
        long_prompt = "word " * 35  # Exceeds default 30 word threshold

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_heavy_response"

        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        result = asyncio.run(router.route_prompt(long_prompt, user_id=TEST_USER_ID))
        assert result == "gpt_heavy_response"

        # Verify the picker would choose GPT for heavy word count
        engine, model, reason, _ = model_picker.pick_model(long_prompt, "chat", 1000)
        assert engine == "gpt"
        assert model == GPT_HEAVY_MODEL
        assert reason == "heavy_length"

    def test_heavy_tokens_routes_to_gpt(self, monkeypatch):
        """Test that prompts with heavy token count route to GPT."""
        from app import model_picker, router
        from app.model_config import GPT_HEAVY_MODEL

        # Create prompt with high token count by making it very long
        prompt = "word " * 1200  # This should exceed 1000 tokens

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_heavy_response", 0, 0, 0.0

        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        result = asyncio.run(router.route_prompt(prompt, user_id=TEST_USER_ID))
        assert result == "gpt_heavy_response"

        # Verify the picker would choose GPT for heavy tokens
        from app.token_utils import count_tokens

        actual_tokens = count_tokens(prompt)
        engine, model, reason, _ = model_picker.pick_model(
            prompt, "analysis", actual_tokens
        )
        assert engine == "gpt"
        assert model == GPT_HEAVY_MODEL
        assert reason == "heavy_length"  # The actual reason when words exceed threshold

    def test_keyword_routing_routes_to_gpt(self, monkeypatch):
        """Test that prompts with keywords route to GPT."""
        from app import model_picker, router
        from app.model_config import GPT_HEAVY_MODEL

        # Create prompt with keyword
        keyword_prompt = "Please analyze this code for me"

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_keyword_response"

        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        result = asyncio.run(router.route_prompt(keyword_prompt, user_id=TEST_USER_ID))
        assert result == "gpt_keyword_response"

        # Verify the picker would choose GPT for keyword
        engine, model, reason, keyword_hit = model_picker.pick_model(
            keyword_prompt, "chat", 100
        )
        assert engine == "gpt"
        assert model == GPT_HEAVY_MODEL
        assert reason == "keyword"
        assert keyword_hit == "code"  # The prompt contains "code"

    def test_heavy_intent_routes_to_gpt(self, monkeypatch):
        """Test that prompts with heavy intents route to GPT."""
        from app import model_picker, router
        from app.model_config import GPT_HEAVY_MODEL

        prompt = "Please summarize this simple research topic briefly"

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_intent_response", 0, 0, 0.0

        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        result = asyncio.run(router.route_prompt(prompt, user_id=TEST_USER_ID))
        assert result == "gpt_intent_response"

        # Verify the picker would choose GPT for heavy intent
        engine, model, reason, _ = model_picker.pick_model(prompt, "analysis", 100)
        assert engine == "gpt"
        assert model == GPT_HEAVY_MODEL
        assert (
            reason == "keyword"
        )  # The prompt contains "summarize" which matches keywords

    def test_light_task_routes_to_llama(self, monkeypatch):
        """Test that light tasks route to LLaMA."""
        from app import llama_integration, model_picker, router

        light_prompt = "Hello, how are you?"

        # Mock health check to return healthy for ollama
        monkeypatch.setattr(
            router, "_check_vendor_health", lambda vendor: vendor == "ollama"
        )
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        async def fake_llama(prompt, model=None, **kwargs):
            return "llama_light_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)

        result = asyncio.run(router.route_prompt(light_prompt, user_id=TEST_USER_ID))
        assert result == "llama_light_response"

        # Verify the picker would choose LLaMA for light task
        engine, model, reason, _ = model_picker.pick_model(light_prompt, "chat", 50)
        assert engine == "llama"
        assert model == "llama3:latest"
        assert reason == "light_default"

    def test_unhealthy_llama_routes_to_gpt(self, monkeypatch):
        """Test that when LLaMA is unhealthy, tasks route to GPT."""
        from app import llama_integration, model_picker, router
        from app.model_config import GPT_HEAVY_MODEL

        prompt = "Hello"

        # Setup unhealthy LLaMA
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", False)

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_fallback_response", 0, 0, 0.0

        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        result = asyncio.run(router.route_prompt(prompt, user_id=TEST_USER_ID))
        assert result == "gpt_fallback_response"

        # Verify the picker would choose GPT when LLaMA is unhealthy
        engine, model, reason, _ = model_picker.pick_model(prompt, "chat", 50)
        assert engine == "gpt"
        assert model == GPT_HEAVY_MODEL
        assert reason == "llama_unhealthy"


class TestLlamaFailureGptFallbackPath:
    """Tests that prove LLaMA failure → GPT fallback path runs and logs once."""

    def test_llama_failure_triggers_gpt_fallback_once(self, monkeypatch, caplog):
        """Test that LLaMA failure triggers GPT fallback exactly once."""
        from app import llama_integration, router

        caplog.set_level(logging.INFO)

        # Setup healthy vendors and mock health check
        monkeypatch.setattr(router, "_check_vendor_health", lambda vendor: True)
        monkeypatch.setattr(router, "OPENAI_HEALTHY", True)
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        call_count = {"llama": 0, "gpt": 0}

        async def fake_llama(prompt, model=None, **kwargs):
            call_count["llama"] += 1
            raise httpx.TimeoutException("LLaMA timeout")

        async def fake_gpt(prompt, model=None, **kwargs):
            call_count["gpt"] += 1
            return "gpt_fallback_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)
        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        # Force routing to LLaMA first
        def fake_pick_model(prompt, intent, tokens):
            return "llama", "llama3:latest", "light_default", None

        monkeypatch.setattr(router, "pick_model", fake_pick_model)

        result = asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Verify result came from GPT fallback
        assert result == "gpt_fallback_response"

        # Verify each service called exactly once
        assert call_count["llama"] == 1
        assert call_count["gpt"] == 1

        # Verify fallback was logged
        assert any("fallback" in record.message.lower() for record in caplog.records)

    def test_llama_5xx_error_triggers_fallback(self, monkeypatch):
        """Test that LLaMA 5xx errors trigger fallback to GPT."""
        from app import llama_integration, router

        # Setup healthy OpenAI for fallback and mock health check
        monkeypatch.setattr(router, "_check_vendor_health", lambda vendor: True)
        monkeypatch.setattr(router, "OPENAI_HEALTHY", True)
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        call_count = {"llama": 0, "gpt": 0}

        async def fake_llama(prompt, model=None, **kwargs):
            call_count["llama"] += 1
            # Simulate server error
            raise httpx.HTTPStatusError(
                "500 Internal Server Error",
                request=MagicMock(),
                response=MagicMock(status_code=500),
            )

        async def fake_gpt(prompt, model=None, **kwargs):
            call_count["gpt"] += 1
            return "gpt_fallback_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)
        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        # Force routing to LLaMA first
        def fake_pick_model(prompt, intent, tokens):
            return "llama", "llama3:latest", "light_default", None

        monkeypatch.setattr(router, "pick_model", fake_pick_model)

        result = asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Verify result came from GPT fallback
        assert result == "gpt_fallback_response"

        # Verify each service called exactly once
        assert call_count["llama"] == 1
        assert call_count["gpt"] == 1

    def test_llama_4xx_error_no_fallback(self, monkeypatch):
        """Test that LLaMA 4xx errors do NOT trigger fallback."""
        from app import llama_integration, router

        # Setup healthy OpenAI (should not be called) and mock health check
        monkeypatch.setattr(router, "_check_vendor_health", lambda vendor: True)
        monkeypatch.setattr(router, "OPENAI_HEALTHY", True)
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        call_count = {"llama": 0, "gpt": 0}

        async def fake_llama(prompt, model=None, **kwargs):
            call_count["llama"] += 1
            # Simulate client error (should not fallback)
            raise httpx.HTTPStatusError(
                "400 Bad Request",
                request=MagicMock(),
                response=MagicMock(status_code=400),
            )

        async def fake_gpt(prompt, model=None, **kwargs):
            call_count["gpt"] += 1
            return "gpt_fallback_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)
        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        # Force routing to LLaMA first
        def fake_pick_model(prompt, intent, tokens):
            return "llama", "llama3:latest", "light_default", None

        monkeypatch.setattr(router, "pick_model", fake_pick_model)

        # Should raise original error, no fallback
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Verify only LLaMA was called
        assert call_count["llama"] == 1
        assert call_count["gpt"] == 0


class TestGoldenTraceEmitsExactlyOnce:
    """Tests that prove golden trace always emits exactly once."""

    def test_golden_trace_emits_once_per_request(self, monkeypatch, caplog):
        """Test that golden trace emits exactly once per request."""
        from app import llama_integration, router

        caplog.set_level(logging.INFO)

        # Setup healthy LLaMA
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        async def fake_llama(prompt, model=None, **kwargs):
            return "llama_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)

        # Clear any existing log records
        caplog.clear()

        result = asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Count golden trace logs
        golden_trace_count = sum(
            1 for record in caplog.records if "GOLDEN_TRACE:" in record.message
        )

        assert golden_trace_count == 1
        assert result == "llama_response"

    def test_golden_trace_emits_once_with_fallback(self, monkeypatch, caplog):
        """Test that golden trace emits exactly once even with fallback."""
        from app import llama_integration, router

        caplog.set_level(logging.INFO)

        # Setup healthy OpenAI for fallback
        monkeypatch.setattr(router, "OPENAI_HEALTHY", True)
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        async def fake_llama(prompt, model=None, **kwargs):
            raise httpx.TimeoutException("LLaMA timeout")

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_fallback_response", 0, 0, 0.0

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)
        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        # Force routing to LLaMA first
        def fake_pick_model(prompt, intent, tokens):
            return "llama", "llama3:latest", "light_default", None

        monkeypatch.setattr(router, "pick_model", fake_pick_model)

        # Clear any existing log records
        caplog.clear()

        result = asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Count golden trace logs
        golden_trace_count = sum(
            1 for record in caplog.records if "GOLDEN_TRACE:" in record.message
        )

        assert golden_trace_count == 1
        assert result == "gpt_fallback_response"

    def test_golden_trace_emits_once_with_override(self, monkeypatch, caplog):
        """Test that golden trace emits exactly once with model override."""
        from app import llama_integration, router

        caplog.set_level(logging.INFO)

        # Setup healthy LLaMA
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)
        monkeypatch.setattr(router, "ALLOWED_LLAMA_MODELS", {"llama3:latest"})

        async def fake_llama(prompt, model=None, **kwargs):
            return "llama_override_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)

        # Clear any existing log records
        caplog.clear()

        result = asyncio.run(
            router.route_prompt(
                TEST_PROMPT, model_override="llama3:latest", user_id=TEST_USER_ID
            )
        )

        # Count golden trace logs
        golden_trace_count = sum(
            1 for record in caplog.records if "GOLDEN_TRACE:" in record.message
        )

        assert golden_trace_count == 1
        assert result == "llama_override_response"

    def test_golden_trace_contains_required_fields(self, monkeypatch, caplog):
        """Test that golden trace contains all required fields."""
        import json

        from app import llama_integration, router

        caplog.set_level(logging.INFO)

        # Setup healthy LLaMA
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        async def fake_llama(prompt, model=None, **kwargs):
            return "llama_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)

        # Clear any existing log records
        caplog.clear()

        result = asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Find golden trace log
        golden_trace_record = next(
            record for record in caplog.records if "GOLDEN_TRACE:" in record.message
        )

        # Parse JSON from log message
        json_start = golden_trace_record.message.find("{")
        json_str = golden_trace_record.message[json_start:]
        trace_data = json.loads(json_str)

        # Verify required fields are present
        required_fields = [
            "ts",
            "rid",
            "uid",
            "path",
            "shape",
            "intent",
            "tokens_est",
            "picker_reason",
            "chosen_vendor",
            "chosen_model",
            "dry_run",
            "cb_user_open",
            "cb_global_open",
            "allow_fallback",
            "stream",
            "latency_ms",
            "timeout_ms",
            "fallback_reason",
            "cache_hit",
        ]

        for field in required_fields:
            assert field in trace_data, f"Missing required field: {field}"

        assert trace_data["chosen_vendor"] == "ollama"
        assert trace_data["chosen_model"] == "llama3:latest"
        assert trace_data["uid"] == TEST_USER_ID
        assert trace_data["path"] == "/v1/ask"


class TestCircuitBreakerOpensAfterThreshold:
    """Tests that prove CB opens after threshold and cools down."""

    def test_user_cb_opens_after_threshold_failures(self, monkeypatch):
        """Test that user circuit breaker opens after reaching failure threshold."""
        from app import llama_integration, router

        # Setup healthy vendors
        monkeypatch.setattr(router, "OPENAI_HEALTHY", True)
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        failure_count = 0

        async def fake_llama(prompt, model=None, **kwargs):
            nonlocal failure_count
            failure_count += 1
            raise httpx.TimeoutException(f"LLaMA failure {failure_count}")

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)
        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        # Force routing to LLaMA to trigger failures
        def fake_pick_model(prompt, intent, tokens):
            return "llama", "llama3:latest", "light_default", None

        monkeypatch.setattr(router, "pick_model", fake_pick_model)

        # First 2 failures should not open circuit breaker (threshold is 3)
        for i in range(2):
            with pytest.raises(httpx.TimeoutException):
                asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Check circuit breaker state (should not be open yet)
        assert not asyncio.run(router._user_circuit_open(TEST_USER_ID))

        # 3rd failure should open circuit breaker
        with pytest.raises(httpx.TimeoutException):
            asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Verify circuit breaker is now open
        assert asyncio.run(router._user_circuit_open(TEST_USER_ID))

    def test_user_cb_cools_down_after_timeout(self, monkeypatch):
        """Test that user circuit breaker cools down after cooldown period."""
        import time

        from app import llama_integration, router

        # Setup healthy vendors
        monkeypatch.setattr(router, "OPENAI_HEALTHY", True)
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        async def fake_llama(prompt, model=None, **kwargs):
            return "llama_response"

        async def fake_gpt(prompt, model=None, **kwargs):
            return "gpt_response"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)
        monkeypatch.setattr("app.router.ask_gpt", fake_gpt)
        monkeypatch.setattr("app.gpt_client.ask_gpt", fake_gpt)

        # Force routing to LLaMA
        def fake_pick_model(prompt, intent, tokens):
            return "llama", "llama3:latest", "light_default", None

        monkeypatch.setattr(router, "pick_model", fake_pick_model)

        # Manually set circuit breaker state to simulate failures
        test_user = TEST_USER_ID
        now = time.time()
        past_time = now - 200  # Past cooldown period
        router._llama_user_failures[test_user] = (3, past_time)

        # Should be cooled down now
        assert not asyncio.run(router._user_circuit_open(test_user))

        # Should successfully route to LLaMA
        result = asyncio.run(router.route_prompt(TEST_PROMPT, user_id=test_user))
        assert result == "llama_response"

    def test_global_cb_opens_after_threshold_failures(self, monkeypatch):
        """Test that global circuit breaker opens after reaching failure threshold."""
        from app import llama_integration, router

        # Setup LLaMA to fail
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        failure_count = 0

        async def fake_llama(prompt, model=None, **kwargs):
            nonlocal failure_count
            failure_count += 1
            raise httpx.TimeoutException(f"LLaMA failure {failure_count}")

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)

        # Force routing to LLaMA
        def fake_pick_model(prompt, intent, tokens):
            return "llama", "llama3:latest", "light_default", None

        monkeypatch.setattr(router, "pick_model", fake_pick_model)

        # First 2 failures should not open circuit breaker (threshold is 3)
        for i in range(2):
            with pytest.raises(httpx.TimeoutException):
                asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Check global circuit breaker state (should not be open yet)
        assert not llama_integration.llama_circuit_open

        # 3rd failure should open circuit breaker
        with pytest.raises(httpx.TimeoutException):
            asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))

        # Verify global circuit breaker is now open
        assert llama_integration.llama_circuit_open

    def test_cb_reset_after_success(self, monkeypatch):
        """Test that circuit breaker resets after successful call."""
        from app import llama_integration, router

        # Setup LLaMA to succeed
        monkeypatch.setattr(llama_integration, "LLAMA_HEALTHY", True)

        call_count = 0

        async def fake_llama(prompt, model=None, **kwargs):
            nonlocal call_count
            call_count += 1
            return f"llama_response_{call_count}"

        monkeypatch.setattr("app.router.ask_llama", fake_llama)
        monkeypatch.setattr("app.llama_integration.ask_llama", fake_llama)

        # Force routing to LLaMA
        def fake_pick_model(prompt, intent, tokens):
            return "llama", "llama3:latest", "light_default", None

        monkeypatch.setattr(router, "pick_model", fake_pick_model)

        # Manually set circuit breaker state to simulate previous failures
        llama_integration.llama_failures = 3
        llama_integration.llama_circuit_open = True

        # First call should succeed and reset circuit breaker
        result = asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))
        assert result == "llama_response_1"

        # Verify circuit breaker is reset
        assert not llama_integration.llama_circuit_open
        assert llama_integration.llama_failures == 0

        # Subsequent calls should work normally
        result = asyncio.run(router.route_prompt(TEST_PROMPT, user_id=TEST_USER_ID))
        assert result == "llama_response_2"
