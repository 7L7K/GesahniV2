# Domain: Router / Ask

## Current Purpose

The Router/Ask domain handles intelligent prompt routing and LLM orchestration for the GesahniV2 application. It provides:

- **Multi-backend routing** with automatic fallback between OpenAI GPT, Ollama LLaMA, and dry-run modes
- **Built-in skills system** with 40+ specialized skills (weather, calendar, music, etc.) that bypass LLMs for deterministic tasks
- **Intent detection** using semantic classification with SBERT embeddings
- **Model selection** based on prompt complexity, keywords, and intent analysis
- **Circuit breaker protection** with per-user and global LLaMA health monitoring
- **Streaming responses** with Server-Sent Events (SSE) support
- **Rate limiting and budget enforcement** with configurable timeouts
- **Semantic caching** to avoid redundant LLM calls
- **Telemetry and observability** with golden trace logging
- **Post-processing hooks** for RAG, skills, and memory integration
- **Idempotency support** with request deduplication
- **Moderation pre-checks** to filter inappropriate content

## Entry Points (Routes, Hooks, Startup Tasks)

### HTTP API Endpoints

- **`/v1/ask`** (POST) → `app.api.ask._ask()` - Main prompt routing endpoint with streaming support
- **`/ask`** (POST) → `app.router.ask_api.ask_endpoint()` - Legacy ask endpoint with backend routing
- **`/ask/dry-explain`** (POST) → `app.api.ask.ask_dry_explain()` - Debug endpoint returning routing decisions without LLM calls
- **`/ask/stream`** (POST) → `app.api.ask.ask_stream()` - Streaming endpoint with SSE routing events
- **`/ask/replay/{rid}`** (GET) → `app.api.ask.ask_replay()` - Debug replay endpoint (placeholder implementation)

### Internal Routing Functions

- **`app.router.route_prompt()`** - Core routing entrypoint with skills check and LLM fallback
- **`app.router.entrypoint.route_prompt()`** - Compatibility bridge supporting registry and DI patterns
- **`app.model_picker.pick_model()`** - Heuristic model selection based on prompt characteristics
- **`app.intent_detector.detect_intent()`** - Hybrid intent classification (heuristics + semantic)
- **`app.skills.base.check_builtin_skills()`** - Skills scoring and selection system

### Startup Tasks

- **Backend factory registration** → `app.routers.register_backend_factory()` - Registers router backends at startup
- **Model validation** → `app.router._validate_model_allowlist()` - Validates model names against allowlists
- **Circuit breaker initialization** → `app.router.start_openai_health_background_loop()` - Background health monitoring
- **Skills initialization** → `app.skills.__init__.SKILLS` - Loads and orders 40+ built-in skills

### WebSocket Integration

- **Streaming callbacks** → `app.api.ask._stream_cb()` - Token streaming for real-time responses
- **SSE wrapper** → `app.api.ask._sse_wrapper()` - Server-Sent Events formatting

## Internal Dependencies

### Core Routing Modules
- **`app.router`** - Main routing logic with fallback chains and health monitoring
- **`app.model_picker`** - Heuristic model selection engine
- **`app.intent_detector`** - Hybrid intent classification system
- **`app.skills.base`** - Skill matching and execution framework
- **`app.prompt_builder`** - Prompt formatting and context assembly
- **`app.token_utils`** - Token counting and budget management

### Backend Routers
- **`app.routers.openai_router`** - OpenAI GPT client with streaming support
- **`app.routers.llama_router`** - Ollama LLaMA client with health checking
- **`app.routers.dryrun_router`** - Mock backend for testing and development

### Skills System
- **`app.skills.selector`** - Scoring-based skill selection algorithm
- **`app.skills.parsers`** - Pattern matching and candidate scoring
- **`app.skills.contracts`** - Skill interface definitions and contracts

### Supporting Infrastructure
- **`app.memory.vector_store`** - Semantic caching and retrieval
- **`app.analytics`** - Request tracking and metrics collection
- **`app.telemetry`** - Structured logging and observability
- **`app.postcall`** - Post-LLM processing hooks
- **`app.observability`** - Tracing and monitoring integration

## External Dependencies

### LLM Providers
- **OpenAI API** - GPT models (gpt-4o, gpt-4, gpt-3.5-turbo) via REST API
- **Ollama** - Local LLaMA models via HTTP API on configurable host/port
- **Dry-run mock** - No external dependency, returns canned responses

### Storage Systems
- **Vector store** - ChromaDB/Qdrant for semantic caching and memory retrieval
- **File system** - History logging and golden trace storage
- **Memory store** - In-process caching for idempotency and deduplication

### Configuration Systems
- **Environment variables** - Routing thresholds, timeouts, model allowlists
- **Router rules YAML** - Optional declarative routing rules (`router_rules.yaml`)
- **Skill registry** - Dynamic skill loading and ordering

### Third-party Services
- **Sentence Transformers** - SBERT embeddings for semantic intent classification
- **RapidFuzz** - Fuzzy string matching for greeting detection
- **HTTPX** - Async HTTP client for LLM provider communication

## Invariants / Assumptions

- **Skills-first routing**: All prompts are checked against built-in skills before LLM routing
- **OpenAI fallback**: LLaMA failures automatically fall back to OpenAI GPT when available
- **Model prefix routing**: Model names must start with "gpt-" or "llama-" for proper routing
- **Health monitoring**: LLaMA health is continuously monitored with circuit breaker protection
- **Token budget enforcement**: All requests respect configurable time and token budgets
- **Streaming compatibility**: All backends must support streaming callbacks or return complete responses
- **Dry-run default**: Unconfigured environments default to dry-run mode for safety
- **Request ID propagation**: All routing decisions include unique request IDs for tracing
- **Semantic caching**: Identical prompts return cached responses when available

## Known Weirdness / Bugs

- **Inconsistent routing contracts**: Multiple entrypoints (`/v1/ask`, `/ask`) with different response formats
- **Dry-run auth bypass**: Authentication is bypassed in dry-run mode, creating security gaps
- **Circuit breaker race conditions**: Global circuit breaker state can be inconsistent under high concurrency
- **Streaming timeout handling**: SSE connections may not properly handle backend timeouts
- **Idempotency cache leaks**: In-memory idempotency cache grows indefinitely without cleanup
- **Skill ordering sensitivity**: SmalltalkSkill must be first to prevent greeting misclassification
- **LLaMA health check blocking**: Health checks can block routing decisions during failures
- **Post-processing hook failures**: Failed hooks don't prevent response delivery but are silently ignored

## Observed Behavior

### Response Formats

**Standard JSON Response:**
```json
{
  "backend": "openai|llama|dryrun",
  "model": "gpt-4o",
  "answer": "Assistant response text",
  "usage": {
    "input_tokens": 150,
    "output_tokens": 75
  },
  "latency_ms": 1250,
  "req_id": "abc123"
}
```

**Streaming SSE Events:**
```
event: route
data: {"rid": "abc123", "chosen_vendor": "openai", "model": "gpt-4o"}

event: delta
data: {"content": "Hello"}

event: done
data: {"rid": "abc123", "final_tokens": 225}
```

### Status Codes and Error Handling

- **200 OK**: Successful routing and response generation
- **400 Bad Request**: Invalid payload format, empty prompts, or moderation violations
- **401 Unauthorized**: Missing authentication for protected endpoints
- **403 Forbidden**: Insufficient scope or model not in allowlist
- **415 Unsupported Media Type**: Non-JSON request body
- **422 Unprocessable Entity**: Malformed request payload
- **429 Too Many Requests**: Rate limiting triggered
- **503 Service Unavailable**: All LLM backends unavailable or circuit breaker open
- **504 Gateway Timeout**: Request exceeded configured budget

### Routing Flow Priority

1. **Cache Check**: Semantic cache lookup for identical prompts
2. **Skills Matching**: 40+ built-in skills checked in priority order
3. **Intent Analysis**: SBERT-based intent classification
4. **Model Selection**: Heuristic routing based on complexity/keywords
5. **Health Validation**: Backend health checks and circuit breaker status
6. **LLM Execution**: Primary backend call with timeout enforcement
7. **Fallback Chain**: Automatic fallback to alternative backends on failure
8. **Post-processing**: RAG, skills, and memory hooks executed
9. **Response Formatting**: Standardized envelope with telemetry data

### Circuit Breaker Behavior

- **LLaMA failures**: Counted per-user and globally with configurable thresholds
- **Cooldown periods**: Failed users blocked for 120 seconds after 3 failures
- **Health monitoring**: Background task probes LLaMA every 5 seconds when circuit open
- **OpenAI fallback**: Automatic fallback to GPT when LLaMA circuit breaker activates

## TODOs / Redesign Ideas

### Immediate Issues
- **Authentication in dry-run**: Implement proper auth when not in dry-run mode (app/router/ask_api.py:139)
- **OpenAI client caching**: Replace mock client creation with real async client caching (app/routers/openai_router.py:24)
- **OpenAI async calls**: Perform real async calls using cached client (app/routers/openai_router.py:48)

### Architecture Improvements
- **Unified routing contract**: Consolidate `/v1/ask` and `/ask` endpoints with consistent response format
- **Streaming reliability**: Improve SSE timeout handling and connection cleanup
- **Circuit breaker consistency**: Fix race conditions in global circuit breaker state
- **Idempotency cleanup**: Implement TTL-based cleanup for in-memory idempotency cache
- **Post-processing error handling**: Add structured error handling for failed hooks
- **Skills dependency injection**: Move skills system to proper DI pattern like router backends

### Observability Enhancements
- **Golden trace replay**: Implement actual replay functionality for debugging (currently placeholder)
- **Metrics cardinality control**: Better normalization of model labels to prevent metrics explosion
- **Error classification**: More granular error categorization for better troubleshooting
- **Performance profiling**: Add detailed timing breakdowns for routing pipeline stages

### Future Capabilities
- **Dynamic skill loading**: Runtime skill discovery and loading without restarts
- **A/B routing experiments**: Framework for testing different routing strategies
- **Model fine-tuning integration**: Support for custom fine-tuned models in routing
- **Multi-region routing**: Geographic routing based on user location and backend availability
- **Cost optimization**: Intelligent routing based on cost per token and user budgets
