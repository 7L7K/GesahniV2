# Extracted Modules Summary

This document summarizes the four modules that were extracted from the existing codebase to improve modularity and separation of concerns.

## 1. `app/router_policy.py` - Router Policy Module

**Purpose**: Handles model routing policies including model picking, allowlist validation, fallback policies, and circuit breaker checks.

### Key Components:

- **RoutingDecision**: Dataclass representing a routing decision with vendor, model, reason, intent, and metadata
- **pick_model_with_policy()**: Main function for model selection with policy-based routing
- **validate_model_allowlist()**: Validates models against allowed lists for each vendor
- **check_vendor_health()**: Checks vendor health based on circuit breaker state
- **should_fallback()**: Determines if fallback should be attempted
- **get_fallback_decision()**: Creates fallback routing decisions

### Features:
- Model override support
- Automatic model picking based on intent and token count
- Allowlist validation for security
- Circuit breaker integration for fault tolerance
- Fallback policy management
- Health check management for OpenAI

### Usage:
```python
from app.router_policy import pick_model_with_policy, RoutingDecision

# Automatic model selection
decision = pick_model_with_policy(
    prompt="What is the weather like?",
    allow_fallback=True
)

# Model override
decision = pick_model_with_policy(
    prompt="Complex analysis task",
    model_override="gpt-4o",
    allow_fallback=False
)
```

## 2. `app/llm_adapters.py` - LLM Adapters Module

**Purpose**: Provides unified interfaces for calling different LLM providers with consistent error handling and response normalization.

### Key Components:

- **LLMRequest**: Standardized request structure for any LLM provider
- **LLMResponse**: Standardized response structure from any LLM provider
- **LLMError**: Base exception class with vendor-specific error types
- **call_openai()**: OpenAI adapter with error normalization
- **call_ollama()**: Ollama adapter with error normalization
- **call_llm()**: Unified interface that routes to appropriate provider

### Error Types:
- **LLMTimeoutError**: Request timeout
- **LLMRateLimitError**: Rate limit exceeded
- **LLMQuotaError**: Quota exceeded
- **LLMProviderError**: Provider-specific errors

### Features:
- Unified request/response interfaces
- Automatic vendor detection (gpt-* for OpenAI, others for Ollama)
- Comprehensive error normalization
- Streaming support
- Metrics integration
- Telemetry spans

### Usage:
```python
from app.llm_adapters import LLMRequest, call_llm, call_openai_simple

# Unified interface
request = LLMRequest(
    prompt="Hello, how are you?",
    model="gpt-4o",
    system_prompt="You are a helpful assistant."
)
response = await call_llm(request)

# Simple interface
response = await call_openai_simple(
    prompt="Hello",
    model="gpt-4o",
    timeout=30.0
)
```

## 3. `app/postcall.py` - Post-Call Processing Module

**Purpose**: Handles all post-call processing including history logging, analytics recording, memory storage, claims writing, and response caching.

### Key Components:

- **PostCallData**: Data structure for post-call processing
- **PostCallResult**: Result structure with processing status
- **process_postcall()**: Main function for comprehensive post-call processing
- **log_history()**: History logging functionality
- **record_analytics()**: Analytics recording
- **store_memory()**: Memory storage with policy enforcement
- **write_claims()**: Claims writing for MemGPT
- **cache_response()**: Response caching

### Features:
- Comprehensive post-call processing
- Selective processing options
- Error handling and reporting
- Memory write policy integration
- Convenience functions for different vendors
- Concurrent processing capabilities

### Usage:
```python
from app.postcall import PostCallData, process_postcall, process_openai_response

# Comprehensive processing
data = PostCallData(
    prompt="What is AI?",
    response="AI is artificial intelligence...",
    vendor="openai",
    model="gpt-4o",
    prompt_tokens=10,
    completion_tokens=20,
    cost_usd=0.01,
    session_id="session123",
    user_id="user123"
)
result = await process_postcall(data)

# Convenience function
result = await process_openai_response(
    prompt="What is AI?",
    response="AI is artificial intelligence...",
    model="gpt-4o",
    prompt_tokens=10,
    completion_tokens=20,
    cost_usd=0.01
)
```

## 4. `app/health.py` - Health Module

**Purpose**: Provides cached health probes and metrics for various system components including LLM providers, vector stores, and other dependencies.

### Key Components:

- **HealthCheckResult**: Result structure for health checks
- **HealthCheckCache**: Cache for health check results
- **check_openai_health()**: OpenAI health check with caching
- **check_ollama_health()**: Ollama health check with caching
- **check_vector_store_health()**: Vector store health check
- **check_home_assistant_health()**: Home Assistant health check
- **check_database_health()**: Database health check
- **check_system_health()**: Comprehensive system health check

### Features:
- Cached health checks to avoid excessive probing
- Configurable TTL for different components
- Latency measurement
- Error reporting and metadata
- Comprehensive system health assessment
- Cache invalidation utilities

### Usage:
```python
from app.health import check_system_health, check_openai_health

# Individual health check
openai_health = await check_openai_health(cache_result=True)

# Comprehensive system health
system_health = await check_system_health(
    include_openai=True,
    include_ollama=True,
    include_vector_store=True,
    cache_results=True
)

# Check if system is healthy
from app.health import is_system_healthy
healthy = is_system_healthy(system_health)
```

## Benefits of Extraction

1. **Modularity**: Each module has a single, well-defined responsibility
2. **Testability**: Individual modules can be tested in isolation
3. **Reusability**: Modules can be used independently in different contexts
4. **Maintainability**: Changes to one aspect don't affect others
5. **Error Handling**: Centralized error handling and normalization
6. **Caching**: Efficient health check caching reduces load
7. **Policy Management**: Centralized routing and fallback policies

## Integration

These modules are designed to work together but can be used independently:

1. **router_policy.py** → **llm_adapters.py**: Routing decisions feed into LLM calls
2. **llm_adapters.py** → **postcall.py**: LLM responses feed into post-call processing
3. **health.py**: Provides health status for all components
4. All modules integrate with existing metrics, telemetry, and logging systems

## Testing

Comprehensive test suite in `tests/unit/test_extracted_modules.py` covers:
- Data structure creation and validation
- Function behavior with mocked dependencies
- Error handling and edge cases
- Integration between modules
- Async functionality

## Migration Path

To use these modules in existing code:

1. Replace direct LLM calls with `llm_adapters.py`
2. Replace routing logic with `router_policy.py`
3. Add post-call processing with `postcall.py`
4. Integrate health checks with `health.py`
5. Update imports and function calls accordingly

The modules maintain backward compatibility where possible and provide clear migration paths for existing functionality.
