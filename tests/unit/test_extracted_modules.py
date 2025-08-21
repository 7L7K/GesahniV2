"""
Tests for extracted modules: router_policy, adapters, postcall, health
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass

from app.router_policy import (
    RoutingDecision,
    pick_model_with_policy,
    validate_model_allowlist,
    check_vendor_health,
    should_fallback,
    get_fallback_decision
)

from app.llm_adapters import (
    LLMRequest,
    LLMResponse,
    LLMError,
    call_openai,
    call_ollama,
    call_llm
)

from app.postcall import (
    PostCallData,
    PostCallResult,
    process_postcall,
    process_openai_response,
    process_ollama_response
)

from app.health import (
    HealthCheckResult,
    HealthCheckCache,
    check_openai_health,
    check_ollama_health,
    check_system_health
)


class TestRouterPolicy:
    """Test router policy module."""
    
    def test_routing_decision_creation(self):
        """Test RoutingDecision dataclass creation."""
        decision = RoutingDecision(
            vendor="openai",
            model="gpt-4o",
            reason="test",
            intent="conversation",
            tokens_est=100
        )
        
        assert decision.vendor == "openai"
        assert decision.model == "gpt-4o"
        assert decision.reason == "test"
        assert decision.intent == "conversation"
        assert decision.tokens_est == 100
        assert decision.allow_fallback is True
        assert decision.dry_run is False
    
    @patch('app.router_policy.detect_intent')
    @patch('app.router_policy.count_tokens')
    @patch('app.router_policy.pick_model')
    def test_pick_model_with_policy_override(self, mock_pick_model, mock_count_tokens, mock_detect_intent):
        """Test model picking with override."""
        mock_detect_intent.return_value = "conversation"
        mock_count_tokens.return_value = 100
        
        decision = pick_model_with_policy(
            prompt="test prompt",
            model_override="gpt-4o",
            allow_fallback=False
        )
        
        assert decision.vendor == "openai"
        assert decision.model == "gpt-4o"
        assert decision.reason == "override"
        assert decision.allow_fallback is False
        assert mock_pick_model.call_count == 0  # Should not call picker with override
    
    @patch('app.router_policy.detect_intent')
    @patch('app.router_policy.count_tokens')
    @patch('app.router_policy.pick_model')
    def test_pick_model_with_policy_automatic(self, mock_pick_model, mock_count_tokens, mock_detect_intent):
        """Test automatic model picking."""
        mock_detect_intent.return_value = "conversation"
        mock_count_tokens.return_value = 100
        mock_pick_model.return_value = ("gpt", "gpt-4o", "heavy_task", None)
        
        decision = pick_model_with_policy(
            prompt="test prompt",
            allow_fallback=True
        )
        
        assert decision.vendor == "openai"
        assert decision.model == "gpt-4o"
        assert decision.reason == "heavy_task"
        assert decision.allow_fallback is True
        mock_pick_model.assert_called_once()
    
    def test_validate_model_allowlist(self):
        """Test model allowlist validation."""
        # Test valid OpenAI model
        assert validate_model_allowlist("gpt-4o", "openai") is True
        
        # Test valid Ollama model (using the default from environment)
        assert validate_model_allowlist("llama3", "ollama") is True
        
        # Test invalid vendor
        with pytest.raises(ValueError, match="Invalid vendor"):
            validate_model_allowlist("gpt-4o", "invalid")
    
    def test_should_fallback(self):
        """Test fallback decision logic."""
        decision = RoutingDecision(
            vendor="openai",
            model="gpt-4o",
            reason="test",
            intent="conversation",
            tokens_est=100,
            allow_fallback=True
        )
        
        # Test with fallback allowed
        assert should_fallback(decision) is False  # Should not fallback if healthy
        
        # Test with fallback disabled
        decision.allow_fallback = False
        assert should_fallback(decision) is False
    
    def test_get_fallback_decision(self):
        """Test fallback decision creation."""
        original = RoutingDecision(
            vendor="openai",
            model="gpt-4o",
            reason="test",
            intent="conversation",
            tokens_est=100
        )
        
        fallback = get_fallback_decision(original)
        
        assert fallback.vendor == "ollama"
        assert fallback.reason == "fallback_ollama"
        assert fallback.allow_fallback is False  # Don't allow double fallback


class TestAdapters:
    """Test adapters module."""
    
    def test_llm_request_creation(self):
        """Test LLMRequest dataclass creation."""
        request = LLMRequest(
            prompt="test prompt",
            model="gpt-4o",
            system_prompt="You are helpful",
            timeout=30.0
        )
        
        assert request.prompt == "test prompt"
        assert request.model == "gpt-4o"
        assert request.system_prompt == "You are helpful"
        assert request.timeout == 30.0
        assert request.stream is False
    
    def test_llm_response_creation(self):
        """Test LLMResponse dataclass creation."""
        response = LLMResponse(
            text="test response",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.01,
            model="gpt-4o",
            vendor="openai"
        )
        
        assert response.text == "test response"
        assert response.prompt_tokens == 10
        assert response.completion_tokens == 20
        assert response.cost_usd == 0.01
        assert response.model == "gpt-4o"
        assert response.vendor == "openai"
    
    def test_llm_error_creation(self):
        """Test LLMError creation."""
        original_error = Exception("test error")
        llm_error = LLMError(
            message="LLM call failed",
            vendor="openai",
            model="gpt-4o",
            original_error=original_error
        )
        
        assert llm_error.vendor == "openai"
        assert llm_error.model == "gpt-4o"
        assert llm_error.original_error == original_error
    
    @patch('app.llm_adapters.call_openai')
    @pytest.mark.asyncio
    async def test_call_llm_openai(self, mock_call_openai):
        """Test unified LLM interface with OpenAI."""
        mock_response = LLMResponse(
            text="test response",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.01,
            model="gpt-4o",
            vendor="openai"
        )
        mock_call_openai.return_value = mock_response
        
        request = LLMRequest(
            prompt="test prompt",
            model="gpt-4o"
        )
        
        response = await call_llm(request)
        
        assert response == mock_response
        mock_call_openai.assert_called_once_with(request)
    
    @patch('app.llm_adapters.call_ollama')
    @pytest.mark.asyncio
    async def test_call_llm_ollama(self, mock_call_ollama):
        """Test unified LLM interface with Ollama."""
        mock_response = LLMResponse(
            text="test response",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.0,
            model="llama3:latest",
            vendor="ollama"
        )
        mock_call_ollama.return_value = mock_response
        
        request = LLMRequest(
            prompt="test prompt",
            model="llama3:latest"
        )
        
        response = await call_llm(request)
        
        assert response == mock_response
        mock_call_ollama.assert_called_once_with(request)


class TestPostCall:
    """Test postcall module."""
    
    def test_postcall_data_creation(self):
        """Test PostCallData dataclass creation."""
        data = PostCallData(
            prompt="test prompt",
            response="test response",
            vendor="openai",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.01,
            session_id="session123",
            user_id="user123"
        )
        
        assert data.prompt == "test prompt"
        assert data.response == "test response"
        assert data.vendor == "openai"
        assert data.model == "gpt-4o"
        assert data.session_id == "session123"
        assert data.user_id == "user123"
    
    def test_postcall_result_creation(self):
        """Test PostCallResult dataclass creation."""
        result = PostCallResult(
            history_logged=True,
            analytics_recorded=True,
            memory_stored=False,
            claims_written=True,
            response_cached=True
        )
        
        assert result.history_logged is True
        assert result.analytics_recorded is True
        assert result.memory_stored is False
        assert result.claims_written is True
        assert result.response_cached is True
        assert result.errors == []
    
    @patch('app.postcall.log_history')
    @patch('app.postcall.record_analytics')
    @patch('app.postcall.store_memory')
    @patch('app.postcall.write_claims')
    @patch('app.postcall.cache_response')
    @pytest.mark.asyncio
    async def test_process_postcall(self, mock_cache, mock_claims, mock_memory, mock_analytics, mock_history):
        """Test postcall processing."""
        mock_history.return_value = True
        mock_analytics.return_value = True
        mock_memory.return_value = True
        mock_claims.return_value = True
        mock_cache.return_value = True
        
        data = PostCallData(
            prompt="test prompt",
            response="test response",
            vendor="openai",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.01
        )
        
        result = await process_postcall(data)
        
        assert result.history_logged is True
        assert result.analytics_recorded is True
        assert result.memory_stored is True
        assert result.claims_written is True
        assert result.response_cached is True
        assert result.errors == []
        
        # Verify all functions were called
        mock_history.assert_called_once_with(data)
        mock_analytics.assert_called_once_with(data)
        mock_memory.assert_called_once_with(data)
        mock_claims.assert_called_once_with(data)
        mock_cache.assert_called_once_with(data)
    
    @patch('app.postcall.process_postcall')
    @pytest.mark.asyncio
    async def test_process_openai_response(self, mock_process):
        """Test OpenAI response processing convenience function."""
        mock_result = PostCallResult(history_logged=True)
        mock_process.return_value = mock_result
        
        result = await process_openai_response(
            prompt="test prompt",
            response="test response",
            model="gpt-4o",
            prompt_tokens=10,
            completion_tokens=20,
            cost_usd=0.01
        )
        
        assert result == mock_result
        mock_process.assert_called_once()
        
        # Verify the data passed to process_postcall
        call_args = mock_process.call_args[0][0]
        assert call_args.prompt == "test prompt"
        assert call_args.response == "test response"
        assert call_args.vendor == "openai"
        assert call_args.model == "gpt-4o"


class TestHealth:
    """Test health module."""
    
    def test_health_check_result_creation(self):
        """Test HealthCheckResult dataclass creation."""
        result = HealthCheckResult(
            healthy=True,
            status="healthy",
            latency_ms=100.0,
            timestamp=1234567890.0
        )
        
        assert result.healthy is True
        assert result.status == "healthy"
        assert result.latency_ms == 100.0
        assert result.timestamp == 1234567890.0
        assert result.error is None
    
    async def test_health_check_cache(self):
        """Test health check cache functionality."""
        cache = HealthCheckCache(default_ttl_seconds=60.0)
        
        result = HealthCheckResult(
            healthy=True,
            status="healthy",
            latency_ms=100.0
        )
        
        # Test setting and getting
        await cache.set("test_key", result)
        cached = await cache.get("test_key")
        
        assert cached == result
        
        # Test cache invalidation
        await cache.invalidate("test_key")
        cached = await cache.get("test_key")
        
        assert cached is None
    
    @patch('app.health.check_openai_health')
    @patch('app.health.check_ollama_health')
    async def test_check_system_health(self, mock_ollama, mock_openai):
        """Test comprehensive system health check."""
        mock_openai.return_value = HealthCheckResult(
            healthy=True,
            status="healthy",
            latency_ms=100.0
        )
        mock_ollama.return_value = HealthCheckResult(
            healthy=True,
            status="healthy",
            latency_ms=200.0
        )
        
        results = await check_system_health(
            include_openai=True,
            include_ollama=True,
            include_vector_store=False,
            include_home_assistant=False,
            include_database=False
        )
        
        assert "openai" in results
        assert "ollama" in results
        assert results["openai"].healthy is True
        assert results["ollama"].healthy is True
        
        mock_openai.assert_called_once()
        mock_ollama.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])
