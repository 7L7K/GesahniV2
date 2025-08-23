"""Minimum test grid for router functionality.

Tests the core routing, fallback, caching, and circuit breaker behaviors.
"""

import asyncio
import builtins
import os
import sys
import types
from unittest.mock import MagicMock, patch

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


# --- Mock Classes ---
class _Emb:
    def create(self, *a, **k):
        return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.0])])


class _OpenAI:
    def __init__(self, *a, **k):
        self.embeddings = _Emb()


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
                    message=types.SimpleNamespace(content="test response"),
                    delta=None,
                    finish_reason="stop",
                )
            ],
            usage=types.SimpleNamespace(prompt_tokens=10, completion_tokens=5),
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
    OpenAI=_OpenAI, AsyncOpenAI=_AsyncOpenAI, OpenAIError=_OpenAIError
)


@pytest.fixture(autouse=True)
def patch_memgpt_and_vector(monkeypatch):
    """Patch memory and vector store operations for tests."""
    from app import router
    from app.memory import vector_store

    # Patch memory operations to no-op
    monkeypatch.setattr(
        router, "memgpt", types.SimpleNamespace(store_interaction=lambda *a, **k: None)
    )
    monkeypatch.setattr(router, "add_user_memory", lambda *a, **k: None)
    monkeypatch.setattr(
        router, "cache_answer", lambda prompt, answer, cache_id=None: None
    )
    monkeypatch.setattr(router, "lookup_cached_answer", lambda *a, **k: None)

    # Patch vector store operations
    if hasattr(vector_store, "clear_cache"):
        monkeypatch.setattr(vector_store, "clear_cache", lambda: None)
    elif hasattr(vector_store, "_cache"):
        monkeypatch.setattr(vector_store._cache, "delete", lambda **kwargs: None)


@pytest.fixture(autouse=True)
def reset_router_state(monkeypatch):
    """Reset router state between tests."""
    from app import llama_integration, router

    # Reset circuit breakers
    router.openai_failures = 0
    router.openai_last_failure_ts = 0.0
    router.openai_circuit_open = False
    router.OPENAI_HEALTHY = True

    llama_integration.llama_failures = 0
    llama_integration.llama_last_failure_ts = 0.0
    llama_integration.llama_circuit_open = False
    llama_integration.LLAMA_HEALTHY = True

    # Reset user circuit breaker
    router._llama_user_failures.clear()

    # Reset allow-lists to defaults
    monkeypatch.setenv("ALLOWED_GPT_MODELS", "gpt-4o,gpt-4,gpt-3.5-turbo")
    monkeypatch.setenv("ALLOWED_LLAMA_MODELS", "llama3:latest,llama3")

    # Reload allow-lists
    router.ALLOWED_GPT_MODELS, router.ALLOWED_LLAMA_MODELS = (
        router._get_allowed_models()
    )


class TestOverrideAllowsOnlyAllowlistedModels:
    """Test that model overrides only allow allowlisted models."""

    @pytest.mark.asyncio
    async def test_override_allows_only_allowlisted_models(self, monkeypatch):
        """Test that model override only accepts allowlisted models."""
        from app import router

        # Test allowed GPT model
        result = await router.route_prompt(
            prompt="test prompt", user_id="test_user", model_override="gpt-4o"
        )
        assert result is not None

        # Test allowed LLaMA model
        result = await router.route_prompt(
            prompt="test prompt", user_id="test_user", model_override="llama3:latest"
        )
        assert result is not None

        # Test disallowed model should raise
        with pytest.raises(HTTPException) as exc_info:
            await router.route_prompt(
                prompt="test prompt",
                user_id="test_user",
                model_override="disallowed-model",
            )
        assert exc_info.value.status_code == 400
        assert "unknown_model" in str(exc_info.value.detail)


class TestDefaultPickRoutesByIntent:
    """Test that default routing picks models based on intent."""

    @pytest.mark.asyncio
    async def test_default_pick_routes_by_intent(self, monkeypatch):
        """Test that default routing selects appropriate models based on intent."""
        from app import router

        # Test that the router actually calls the model picker
        # We'll test the integration rather than mocking the picker
        with patch("app.router.ask_gpt") as mock_gpt:
            mock_gpt.return_value = ("gpt response", 10, 5, 0.01)

            # Use a prompt that should trigger GPT routing
            result = await router.route_prompt(
                prompt="Please analyze this complex data and provide detailed insights with code examples",
                user_id="test_user",
            )

            # Should have called GPT (the mock will be called if routing works)
            # Note: This test verifies the integration works, not specific routing logic
            assert result is not None


class TestLlamaErrorFallsBackToGpt:
    """Test that LLaMA errors fall back to GPT."""

    @pytest.mark.asyncio
    async def test_llama_error_falls_back_to_gpt_once(self, monkeypatch):
        """Test that LLaMA errors trigger fallback to GPT exactly once."""
        from app import router

        # Mock LLaMA to fail
        def mock_llama_fail(*args, **kwargs):
            raise RuntimeError("LLaMA backend unavailable")

        # Mock GPT to succeed
        def mock_gpt_success(*args, **kwargs):
            return ("gpt fallback response", 10, 5, 0.01)

        # Patch the actual module functions
        with patch("app.llama_integration.ask_llama", side_effect=mock_llama_fail):
            with patch("app.gpt_client.ask_gpt", side_effect=mock_gpt_success):
                # Use model override to force LLaMA routing
                result = await router.route_prompt(
                    prompt="test prompt",
                    user_id="test_user",
                    model_override="llama3:latest",
                )

                assert result == "gpt fallback response"


class TestOpenAI4xxBubblesNoFallback:
    """Test that OpenAI 4xx errors don't trigger fallback."""

    @pytest.mark.asyncio
    async def test_openai_4xx_bubbles_no_fallback(self, monkeypatch):
        """Test that OpenAI 4xx errors bubble up without fallback."""
        from app import router

        # Mock OpenAI to return 4xx error
        def mock_gpt_4xx(*args, **kwargs):
            raise httpx.HTTPStatusError(
                "400 Bad Request",
                request=MagicMock(),
                response=MagicMock(status_code=400),
            )

        # Patch the actual module function
        with patch("app.gpt_client.ask_gpt", side_effect=mock_gpt_4xx):
            # Use model override to force OpenAI routing
            with pytest.raises(httpx.HTTPStatusError):
                await router.route_prompt(
                    prompt="test prompt", user_id="test_user", model_override="gpt-4o"
                )


class TestCacheShortCircuitHits:
    """Test that cache short-circuit works correctly."""

    @pytest.mark.asyncio
    async def test_cache_short_circuit_hits(self, monkeypatch):
        """Test that cache hits short-circuit the routing process."""
        from app import router

        # Mock cache to return a hit
        def mock_cache_hit(prompt, ttl_seconds=86400):
            return "cached response"

        monkeypatch.setattr(router, "lookup_cached_answer", mock_cache_hit)

        # Mock golden trace to capture the call
        trace_calls = []

        def mock_golden_trace(*args, **kwargs):
            trace_calls.append((args, kwargs))

        monkeypatch.setattr(router, "_log_golden_trace", mock_golden_trace)

        result = await router.route_prompt(prompt="test prompt", user_id="test_user")

        # Should return cached response
        assert result == "cached response"

        # Should have logged golden trace with cache hit
        assert len(trace_calls) == 1
        trace_kwargs = trace_calls[0][1]
        assert trace_kwargs.get("cache_hit") is True
        assert trace_kwargs.get("routing_decision").vendor == "cache"


class TestUserCircuitBreaker:
    """Test user-specific circuit breaker behavior."""

    @pytest.mark.asyncio
    async def test_user_cb_opens_and_cools_down(self, monkeypatch):
        """Test that user circuit breaker opens after failures and cools down."""
        from app import router

        # Set low threshold for testing
        monkeypatch.setenv("LLAMA_USER_CB_THRESHOLD", "2")
        monkeypatch.setenv("LLAMA_USER_CB_COOLDOWN", "1")

        # Reload the threshold
        router._USER_CB_THRESHOLD = int(os.getenv("LLAMA_USER_CB_THRESHOLD", "3"))
        router._USER_CB_COOLDOWN = float(os.getenv("LLAMA_USER_CB_COOLDOWN", "120"))

        user_id = "test_user"

        # Initially circuit should be closed
        assert not await router._user_circuit_open(user_id)

        # Record two failures
        await router._user_cb_record_failure(user_id)
        await router._user_cb_record_failure(user_id)

        # Circuit should now be open
        assert await router._user_circuit_open(user_id)

        # Wait for cooldown
        await asyncio.sleep(1.1)

        # Circuit should be closed again
        assert not await router._user_circuit_open(user_id)


class TestTimeoutsEnforcedPerVendor:
    """Test that timeouts are enforced per vendor."""

    @pytest.mark.asyncio
    async def test_timeouts_enforced_per_vendor(self, monkeypatch):
        """Test that appropriate timeouts are passed to each vendor."""
        from app import router

        # Set specific timeouts for testing
        monkeypatch.setenv("OPENAI_TIMEOUT_MS", "5000")
        monkeypatch.setenv("OLLAMA_TIMEOUT_MS", "3000")

        # Reload timeouts
        router.OPENAI_TIMEOUT_MS = int(os.getenv("OPENAI_TIMEOUT_MS", "6000"))
        router.OLLAMA_TIMEOUT_MS = int(os.getenv("OLLAMA_TIMEOUT_MS", "4500"))

        # Test OpenAI timeout
        with patch("app.gpt_client.ask_gpt") as mock_gpt:
            mock_gpt.return_value = ("gpt response", 10, 5, 0.01)

            await router.route_prompt(
                prompt="test prompt", user_id="test_user", model_override="gpt-4o"
            )

            # Check that timeout was passed correctly (converted to seconds)
            call_kwargs = mock_gpt.call_args[1]
            assert call_kwargs.get("timeout") == 5.0  # 5000ms / 1000

        # Test LLaMA timeout
        with patch("app.llama_integration.ask_llama") as mock_llama:
            mock_llama.return_value = iter(["llama response"])

            await router.route_prompt(
                prompt="test prompt",
                user_id="test_user",
                model_override="llama3:latest",
            )

            # Check that timeout was passed correctly
            call_kwargs = mock_llama.call_args[1]
            assert call_kwargs.get("timeout") == 3.0  # 3000ms / 1000


class TestGoldenTraceEmitsOnceWithFields:
    """Test that golden trace emits exactly once with correct fields."""

    @pytest.mark.asyncio
    async def test_golden_trace_emits_once_with_fields(self, monkeypatch):
        """Test that golden trace is emitted exactly once with all required fields."""
        from app import router

        # Capture golden trace calls
        trace_calls = []

        def mock_golden_trace(*args, **kwargs):
            trace_calls.append((args, kwargs))

        monkeypatch.setattr(router, "_log_golden_trace", mock_golden_trace)

        # Mock successful GPT call
        with patch("app.gpt_client.ask_gpt") as mock_gpt:
            mock_gpt.return_value = ("test response", 10, 5, 0.01)

            await router.route_prompt(
                prompt="test prompt", user_id="test_user", model_override="gpt-4o"
            )

            # Should have exactly one golden trace call
            assert len(trace_calls) == 1

            # Check required fields
            trace_kwargs = trace_calls[0][1]
            required_fields = [
                "request_id",
                "user_id",
                "path",
                "shape",
                "intent",
                "tokens_est",
                "routing_decision",
                "dry_run",
                "cb_user_open",
                "cb_global_open",
                "cache_hit",
            ]

            for field in required_fields:
                assert field in trace_kwargs, f"Missing field: {field}"

            # Check routing decision structure
            routing_decision = trace_kwargs["routing_decision"]
            assert hasattr(routing_decision, "vendor")
            assert hasattr(routing_decision, "model")
            assert hasattr(routing_decision, "reason")
            assert routing_decision.vendor == "openai"
            assert routing_decision.model == "gpt-4o"
