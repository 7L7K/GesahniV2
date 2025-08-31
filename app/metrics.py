from prometheus_client import Counter, Histogram
try:
    from prometheus_client import Gauge
except Exception:  # pragma: no cover - optional dependency
    Gauge = None  # type: ignore

SPOTIFY_REQUESTS = Counter(
    "integration_spotify_requests_total",
    "Spotify requests",
    ["method", "path", "status"],
)

SPOTIFY_429 = Counter(
    "integration_spotify_rate_limited_total",
    "Spotify 429s",
    ["path"],
)

SPOTIFY_REFRESH = Counter(
    "integration_spotify_auth_refresh_total",
    "Spotify token refreshes",
)

# OAuth flow metrics
OAUTH_START = Counter(
    "oauth_start_total",
    "OAuth flow starts",
    ["provider"],
)

OAUTH_CALLBACK = Counter(
    "oauth_callback_total",
    "OAuth callback results",
    ["result", "reason"],
)

OAUTH_IDEMPOTENT = Counter(
    "oauth_idempotent_hit_total",
    "OAuth idempotent hits",
)

SPOTIFY_REFRESH_ERROR = Counter(
    "spotify_refresh_error_total",
    "Spotify refresh errors",
)

# Token Store Metrics
TOKEN_STORE_OPERATIONS = Counter(
    "token_store_operations_total",
    "Token store operations",
    ["operation", "provider", "result"]
)

TOKEN_REFRESH_OPERATIONS = Counter(
    "token_refresh_operations_total",
    "Token refresh operations",
    ["provider", "result", "attempt"]
)

# Google OAuth specific metrics
GOOGLE_CONNECT_STARTED = Counter(
    "google_connect_started_total",
    "Google connect flow started",
    ["user_id", "scopes_hash"],
)

GOOGLE_CONNECT_AUTHORIZE_URL_ISSUED = Counter(
    "google_connect_authorize_url_issued_total",
    "Google authorize URL issued",
    ["user_id", "scopes_hash"],
)

GOOGLE_CALLBACK_SUCCESS = Counter(
    "google_callback_success_total",
    "Google callback success",
    ["user_id", "scopes_hash"],
)

GOOGLE_CALLBACK_FAILED = Counter(
    "google_callback_failed_total",
    "Google callback failed",
    ["user_id", "reason"],
)

GOOGLE_REFRESH_SUCCESS = Counter(
    "google_refresh_success_total",
    "Google token refresh success",
    ["user_id"],
)

GOOGLE_REFRESH_FAILED = Counter(
    "google_refresh_failed_total",
    "Google token refresh failed",
    ["user_id", "reason"],
)

GOOGLE_DISCONNECT_SUCCESS = Counter(
    "google_disconnect_success_total",
    "Google disconnect success",
    ["user_id"],
)

SPOTIFY_LATENCY = Histogram(
    "integration_spotify_latency_seconds",
    "Spotify latency",
    ["method", "path"],
)

# Spotify-specific action counters
SPOTIFY_PLAY_COUNT = Counter(
    "spotify_play_count_total",
    "Spotify play requests",
    ["status"],
)

SPOTIFY_DEVICE_LIST_COUNT = Counter(
    "spotify_device_list_count_total",
    "Spotify device list requests",
    ["status"],
)

# Phase 6.1: Clean Prometheus Metrics (no sampling)
# Phase 7.6: Label Hygiene & Cardinality Management

# Auth core scaffolding metrics (Phase 2)
AUTH_LAZY_REFRESH = Counter(
    "auth_lazy_refresh_total", "Lazy AT refresh events", ["source", "result"]
)

AUTH_RT_REJECT = Counter(
    "auth_rt_reject_total", "Refresh token rejected", ["reason"]
)

AUTH_STORE_OUTAGE = Counter(
    "auth_store_outage_total", "Session store outage detections"
)

AUTH_STATUS_LATENCY = Histogram(
    "auth_status_latency_ms", "Auth resolution latency (ms)"
)

AUTH_IDENTITY_RESOLVE = Counter(
    "auth_identity_resolve_total",
    "Auth identity resolution outcome",
    ["source", "result"],
)


def normalize_model_label(model: str) -> str:
    """
    Normalize model names to prevent cardinality explosion.
    Maps specific model names to normalized categories.
    """
    if not model:
        return "unknown"

    model_lower = model.lower()

    # OpenAI GPT models
    if "gpt-4o" in model_lower or "gpt-4-turbo" in model_lower:
        return "gpt4"
    elif "gpt-4" in model_lower:
        return "gpt4"
    elif "gpt-3.5" in model_lower:
        return "gpt35"

    # LLaMA models
    elif "llama3" in model_lower:
        return "llama3"
    elif "llama2" in model_lower:
        return "llama2"
    elif "llama" in model_lower:
        return "llama"

    # Anthropic models
    elif "claude-3" in model_lower or "claude-3-5" in model_lower:
        return "claude3"
    elif "claude" in model_lower:
        return "claude"

    # Fallback: extract provider from model name
    if ":" in model:
        provider = model.split(":")[0].lower()
        if provider in ["openai", "ollama", "anthropic", "cohere", "ai21"]:
            return provider

    # Last resort: hash to prevent unbounded cardinality
    return f"model_{hash(model) % 1000}"


def normalize_shape_label(shape: str) -> str:
    """
    Normalize shape representations to prevent cardinality explosion.
    Categorizes shapes instead of using raw string representations.
    """
    if not shape:
        return "empty"

    shape_lower = shape.lower()

    # Common shape patterns
    if "chat" in shape_lower or "completion" in shape_lower:
        return "chat_completion"
    elif "embedding" in shape_lower:
        return "embedding"
    elif "image" in shape_lower:
        return "image_generation"
    elif "audio" in shape_lower or "tts" in shape_lower:
        return "audio_synthesis"
    elif "stream" in shape_lower:
        return "streaming"
    else:
        # For unknown shapes, categorize by length to limit cardinality
        length = len(shape)
        if length < 50:
            return "short_shape"
        elif length < 200:
            return "medium_shape"
        else:
            return "long_shape"


try:
    from prometheus_client import Counter, Histogram
except Exception:  # pragma: no cover - optional dependency

    class _MetricStub:
        def __init__(self, name, *a, **k):
            self.name = name
            self.value = 0.0

        def labels(self, *a, **k):
            return self

        def inc(self, amount: float = 1.0):
            self.value += amount

        def observe(self, amount: float):
            self.value += amount

    Counter = Histogram = _MetricStub
    class _GaugeStub:
        def __init__(self, name, *a, **k):
            self.name = name
            self.value = 0.0

        def labels(self, *a, **k):
            return self

        def set(self, amount: float):
            self.value = amount

    Gauge = _GaugeStub  # type: ignore

# 6.1.a Core HTTP Metrics
# Requests by route & method & status
REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=("route", "method", "status"),
)

# Skill & selector metrics
SKILL_HITS_TOTAL = Counter(
    "skill_hits_total",
    "Total skill activations",
    ["skill"],
)

SELECTOR_LATENCY_MS = Histogram(
    "selector_latency_ms",
    "Latency of skill selector in milliseconds",
    buckets=(1, 2, 5, 10, 20, 50, 100),
)

SKILL_CONF_BUCKET = Histogram(
    "skill_conf_bucket",
    "Skill confidence buckets",
    buckets=(0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)

LLM_FALLBACK_TOTAL = Counter("llm_fallback_total", "LLM fallback invocations")

UNDO_INVOCATIONS_TOTAL = Counter("undo_invocations_total", "Undo actions invoked")

ENTITY_DISAMBIGUATIONS_TOTAL = Counter("entity_disambiguations_total", "Entity disambiguation events")

# Latency per route
LATENCY = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency (seconds)",
    labelnames=("route", "method"),
    buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

# Auth/RBAC signals
AUTH_FAIL = Counter(
    "auth_fail_total",
    "Authentication failures",
    labelnames=("reason",),  # e.g., "missing_token", "expired", "invalid"
)

# Auth refresh operations
AUTH_REFRESH_OK = Counter(
    "auth_refresh_ok_total",
    "Successful auth refresh operations",
)

AUTH_REFRESH_FAIL = Counter(
    "auth_refresh_fail_total",
    "Failed auth refresh operations",
    labelnames=("reason",),  # e.g., "replay", "concurrent", "expired", "invalid"
)

# Whoami operations
WHOAMI_OK = Counter(
    "whoami_ok_total",
    "Successful whoami operations",
)

WHOAMI_FAIL = Counter(
    "whoami_fail_total",
    "Failed whoami operations",
    labelnames=("reason",),  # e.g., "missing_token", "expired", "invalid"
)

RBAC_DENY = Counter(
    "rbac_deny_total",
    "Authorization (scope) denials",
    labelnames=("scope",),
)

# Rate limiting
RATE_LIMITED = Counter(
    "rate_limited_total",
    "Requests rejected by rate limit",
    labelnames=("route",),
)

# Legacy compatibility - keep existing metrics for backward compatibility
REQUEST_COUNT = Counter(
    "app_request_total", "Total number of requests", ["endpoint", "method", "engine"]
)

REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint", "method", "engine"],
)

# Map to new canonical names for compatibility
GESAHNI_REQUESTS_TOTAL = REQUESTS
GESAHNI_LATENCY_SECONDS = LATENCY

# Health probe metrics ---------------------------------------------------------
try:
    HEALTH_CHECK_DURATION_SECONDS = Histogram(
        "gesahni_health_check_duration_seconds",
        "Health check duration in seconds",
        ["check_type"],
    )
except Exception:  # pragma: no cover

    class _H2:
        def labels(self, *a, **k):
            return self

        def observe(self, *a, **k):
            return None

    HEALTH_CHECK_DURATION_SECONDS = _H2()  # type: ignore

# Simple health gauges
try:
    HEALTH_OK = Gauge("health_ok", "Overall backend health ok (1/0)")
    HEALTH_DEPS_OK = Gauge("health_deps_ok", "Dependency health ok (1/0)", ["component"])
except Exception:  # pragma: no cover

    class _G:
        def labels(self, *a, **k):
            return self

        def set(self, *a, **k):
            return None

    HEALTH_OK = HEALTH_DEPS_OK = _G()  # type: ignore

# Authentication metrics -------------------------------------------------------
try:
    WHOAMI_CALLS_TOTAL = Counter(
        "whoami_calls_total",
        "Total number of whoami endpoint calls",
        ["status", "source", "boot_phase"],
    )
except Exception:  # pragma: no cover

    class _C2:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    WHOAMI_CALLS_TOTAL = _C2()  # type: ignore

try:
    FINISH_CALLS_TOTAL = Counter(
        "finish_calls_total",
        "Total number of auth finish endpoint calls",
        ["status", "method", "reason"],
    )
except Exception:  # pragma: no cover

    class _C3:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    FINISH_CALLS_TOTAL = _C3()  # type: ignore

# Ask endpoint auth metrics
try:
    AUTH_401_TOTAL = Counter(
        "auth_401_total",
        "401 responses by route",
        ["route", "reason"],  # reason: no_auth|bad_token
    )
    AUTH_403_TOTAL = Counter(
        "auth_403_total",
        "403 responses by route",
        ["route", "scope"],
    )
except Exception:  # pragma: no cover

    class _C401:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    AUTH_401_TOTAL = AUTH_403_TOTAL = _C401()  # type: ignore

# Spotify-specific counters for Phase 6
try:
    SPOTIFY_OAUTH_START = Counter("spotify_oauth_start_total", "Spotify OAuth starts", ["provider"])
    SPOTIFY_OAUTH_CALLBACK = Counter("spotify_oauth_callback_total", "Spotify OAuth callback results", ["result", "reason"])
    SPOTIFY_OAUTH_IDEMPOTENT = Counter("spotify_oauth_idempotent_total", "Spotify OAuth idempotent hits")
except Exception:
    SPOTIFY_OAUTH_START = SPOTIFY_OAUTH_CALLBACK = SPOTIFY_OAUTH_IDEMPOTENT = Counter

try:
    PRIVILEGED_CALLS_BLOCKED_TOTAL = Counter(
        "privileged_calls_blocked_total",
        "Total number of privileged calls blocked due to authentication",
        ["endpoint", "reason"],
    )
except Exception:  # pragma: no cover

    class _C4:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    PRIVILEGED_CALLS_BLOCKED_TOTAL = _C4()  # type: ignore

try:
    WS_RECONNECT_ATTEMPTS_TOTAL = Counter(
        "ws_reconnect_attempts_total",
        "Total number of WebSocket reconnection attempts",
        ["endpoint", "reason"],
    )
except Exception:  # pragma: no cover

    class _C5:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    WS_RECONNECT_ATTEMPTS_TOTAL = _C5()  # type: ignore

# Authentication event timing
try:
    AUTH_EVENT_DURATION_SECONDS = Histogram(
        "auth_event_duration_seconds",
        "Authentication event duration in seconds",
        ["event_type", "status"],
    )
except Exception:  # pragma: no cover

    class _H3:
        def labels(self, *a, **k):
            return self

        def observe(self, *a, **k):
            return None

    AUTH_EVENT_DURATION_SECONDS = _H3()  # type: ignore

try:
    HEALTH_READY_FAILURES_TOTAL = Counter(
        "gesahni_health_ready_failures_total",
        "Health readiness failures",
        ["reason"],
    )
except Exception:  # pragma: no cover

    class _C2:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    HEALTH_READY_FAILURES_TOTAL = _C2()  # type: ignore

try:
    ROUTER_SHAPE_NORMALIZED_TOTAL = Counter(
        "gesahni_router_shape_normalized_total",
        "Router shape normalization events",
        ["from_shape", "to_shape"],
    )
except Exception:  # pragma: no cover

    class _C3:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    ROUTER_SHAPE_NORMALIZED_TOTAL = _C3()  # type: ignore

try:
    ROUTER_REQUESTS_TOTAL = Counter(
        "gesahni_router_requests_total",
        "Count of routed requests",
        ["vendor", "model", "reason"],
    )
except Exception:  # pragma: no cover

    class _C4:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    ROUTER_REQUESTS_TOTAL = _C4()  # type: ignore

try:
    ROUTER_FALLBACKS_TOTAL = Counter(
        "gesahni_router_fallbacks_total",
        "Fallbacks between vendors",
        ["from_vendor", "to_vendor", "reason"],
    )
except Exception:  # pragma: no cover

    class _C5:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    ROUTER_FALLBACKS_TOTAL = _C5()  # type: ignore

try:
    ROUTER_CIRCUIT_OPEN_TOTAL = Counter(
        "gesahni_router_circuit_open_total",
        "Circuit breaker openings",
        ["scope"],
    )
except Exception:  # pragma: no cover

    class _C6:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    ROUTER_CIRCUIT_OPEN_TOTAL = _C6()  # type: ignore

try:
    ROUTER_DURATION_MS = Histogram(
        "gesahni_router_duration_ms",
        "Request duration in milliseconds",
        ["vendor", "model"],
    )
except Exception:  # pragma: no cover

    class _H2:
        def labels(self, *a, **k):
            return self

        def observe(self, *a, **k):
            return None

    ROUTER_DURATION_MS = _H2()  # type: ignore

try:
    ROUTER_ASK_USER_ID_MISSING_TOTAL = Counter(
        "gesahni_router_ask_user_id_missing_total",
        "Count of /v1/ask requests with missing user_id",
        ["env", "route"],
    )
except Exception:  # pragma: no cover

    class _C7:
        def labels(self, *a, **k):
            return self

        def inc(self, *a, **k):
            return None

    ROUTER_ASK_USER_ID_MISSING_TOTAL = _C7()  # type: ignore

# Histogram for request cost in USD
REQUEST_COST = Histogram(
    "app_request_cost_usd",
    "Request cost in USD",
    ["endpoint", "method", "engine", "segment"],
)
# Auth and validation spikes (route scoped)
AUTH_4XX_TOTAL = Counter("auth_4xx_total", "Total 4xx auth failures", ["route", "code"])
VALIDATION_4XX_TOTAL = Counter(
    "validation_4xx_total", "Total 4xx validation failures", ["route", "code"]
)

# Counter for LLaMA prompt/completion tokens
LLAMA_TOKENS = Counter("llama_tokens", "Number of LLaMA tokens", ["direction"])

# Histogram for LLaMA call latency in milliseconds
LLAMA_LATENCY = Histogram(
    "llama_latency_ms",
    "Latency of LLaMA generations in milliseconds",
)

# Router decision counts by rule/reason label
ROUTER_DECISION = Counter("router_decision_total", "Routing decisions made", ["rule"])

# Model latency seconds (enables p50/p95 per model in Grafana)
MODEL_LATENCY_SECONDS = Histogram(
    "model_latency_seconds", "LLM model call latency (seconds)", ["model"]
)

# Counter for user memory additions
USER_MEMORY_ADDS = Counter(
    "user_memory_add_total",
    "Number of user memories added",
    ["store", "user"],
)

# Counter for dual-read fallback hits (observability during migration)

# ----------------------------
# PHASE 6: Enhanced Observability Metrics
# ----------------------------

# Per-scope request metrics
SCOPE_REQUESTS_TOTAL = Counter(
    "gesahni_scope_requests_total",
    "Total requests by scope and endpoint",
    ["scope", "route", "method", "status"],
)

# Authorization failure metrics
AUTH_FAILURES_TOTAL = Counter(
    "gesahni_auth_failures_total",
    "Authentication and authorization failures",
    ["type", "route", "reason"],  # type: 401|403|429, reason: specific error
)

# Per-scope latency metrics
SCOPE_LATENCY_SECONDS = Histogram(
    "gesahni_scope_latency_seconds",
    "Request latency by scope in seconds",
    ["scope", "route", "method"],
)

# Rate limit metrics by scope
SCOPE_RATE_LIMITS_TOTAL = Counter(
    "gesahni_scope_rate_limits_total",
    "Rate limit events by scope",
    ["scope", "route", "action"],  # action: allowed|blocked
)

# Audit trail metrics
AUDIT_EVENTS_TOTAL = Counter(
    "gesahni_audit_events_total",
    "Audit trail events",
    ["action", "user_type"],  # user_type: authenticated|anonymous|admin
)

# WebSocket metrics (enhanced)
WS_CONNECTIONS_TOTAL = Counter(
    "gesahni_ws_connections_total",
    "WebSocket connections by scope",
    ["scope", "endpoint", "action"],  # action: connect|disconnect|error
)

WS_MESSAGES_TOTAL = Counter(
    "gesahni_ws_messages_total",
    "WebSocket messages by scope",
    ["scope", "endpoint", "direction"],  # direction: inbound|outbound
)

# Granular scope usage metrics
SCOPE_USAGE_TOTAL = Counter(
    "gesahni_scope_usage_total",
    "Individual scope usage tracking",
    ["scope", "route", "result"],  # result: granted|denied|error
)

# ----------------------------
# TTS-specific metrics
# ----------------------------

# Number of TTS requests by engine and tier
TTS_REQUEST_COUNT = Counter(
    "tts_request_total",
    "Total TTS synthesis requests",
    ["engine", "tier", "mode", "intent", "variant"],
)

# TTS latency (seconds) by engine and tier
TTS_LATENCY_SECONDS = Histogram(
    "tts_latency_seconds",
    "TTS synthesis latency in seconds",
    ["engine", "tier"],
)

# TTS cost (USD)
TTS_COST_USD = Histogram(
    "tts_cost_usd",
    "Estimated TTS cost in USD",
    ["engine", "tier"],
)

# TTS fallbacks between engines
TTS_FALLBACKS = Counter(
    "tts_fallback_total",
    "Number of TTS fallbacks due to errors or policy",
    ["from_engine", "to_engine", "reason"],
)

VECTOR_FALLBACK_READS = Counter(
    "vector_fallback_reads_total",
    "Dual-read fallback hits to secondary store",
    ["area"],  # memory | qa
)

# Vector store init selection/fallback observability -------------------------

VECTOR_SELECTED_TOTAL = Counter(
    "vector_selected_total",
    "Vector store selected at initialization",
    ["backend"],  # memory | chroma | qdrant | dual | cloud
)

VECTOR_INIT_FALLBACKS = Counter(
    "vector_init_fallbacks_total",
    "Vector store initialization fallbacks (non-fatal)",
    ["requested", "reason"],
)

# Care & Device Health metrics -------------------------------------------------
TIME_TO_ACK_SECONDS = Histogram(
    "care_time_to_ack_seconds", "Seconds from alert create to acknowledge"
)
ALERT_SEND_FAILURES = Counter(
    "care_alert_send_failures_total", "Total number of alert send failures", ["channel"]
)
HEARTBEAT_OK = Counter("care_heartbeat_ok_total", "Number of on-time device heartbeats")
HEARTBEAT_LATE = Counter(
    "care_heartbeat_late_total", "Number of late/missed device heartbeats"
)

# Care SMS queue metrics
CARE_SMS_RETRIES = Counter("care_sms_retries_total", "Number of SMS retry attempts")
CARE_SMS_DLQ = Counter(
    "care_sms_dead_letter_total", "Number of SMS jobs sent to dead-letter queue"
)

# ----------------------------
# Rate limit metrics
# ----------------------------

RATE_LIMIT_ALLOWS = Counter(
    "rate_limit_allow_total",
    "Requests allowed by the rate limiter",
    [
        "channel",
        "bucket",
        "backend",
    ],  # channel: http|ws; bucket: burst|long|daily|bypass
)

RATE_LIMIT_BLOCKS = Counter(
    "rate_limit_block_total",
    "Requests blocked by the rate limiter",
    ["channel", "bucket", "backend"],
)

# ----------------------------
# Music observability
# ----------------------------
MUSIC_CMD_LATENCY = Histogram(
    "music_cmd_latency_ms",
    "Music command latency in milliseconds",
    ["verb", "provider"],
    buckets=(5, 10, 25, 50, 100, 200, 500, 1000, 2000),
)

MUSIC_TRANSFER_FAIL_TOTAL = Counter(
    "music_transfer_fail_total",
    "Failures when transferring playback to a device",
    ["reason"],
)

MUSIC_RATE_LIMITED_TOTAL = Counter(
    "music_rate_limited_total",
    "Rate limited events from providers",
    ["provider"],
)

MUSIC_FIRST_SOUND_MS = Histogram(
    "music_first_sound_ms",
    "Time to first audible sound in milliseconds",
    ["route"],
    buckets=(50, 100, 200, 500, 1000, 2000, 5000),
)

MUSIC_RECO_HIT = Counter(
    "music_reco_hit_total",
    "Recommendation cache hits",
    ["vibe"],
)

MUSIC_RECO_MISS = Counter(
    "music_reco_miss_total",
    "Recommendation cache misses",
    ["vibe"],
)

# ----------------------------
# Dependency and vector metrics
# ----------------------------

# Latency for external dependencies (e.g., qdrant, openai, home-assistant)
DEPENDENCY_LATENCY_SECONDS = Histogram(
    "dependency_latency_seconds",
    "External dependency latency (seconds)",
    ["dependency", "operation"],
)

# Embedding latency by backend (openai | llama | stub)
EMBEDDING_LATENCY_SECONDS = Histogram(
    "embedding_latency_seconds",
    "Embedding call latency (seconds)",
    ["backend"],
)

# Vector store operation latency (backend-specific ops aggregated)
VECTOR_OP_LATENCY_SECONDS = Histogram(
    "vector_op_latency_seconds",
    "Vector store operation latency (seconds)",
    ["operation"],
)

# --- Resilience metrics expected by tests ------------------------------------
# These are declared but not necessarily emitted everywhere; tests only verify
# the presence of the metric names in the scrape output.
WS_RECONNECT = Counter(
    "ws_reconnect_total", "Number of WebSocket reconnects", ["reason"]
)
WS_TIME_TO_RECONNECT_SECONDS = Histogram(
    "ws_time_to_reconnect_seconds", "Time to reconnect after WS drop (seconds)"
)
SSE_FAIL_TOTAL = Counter("sse_fail_total", "Number of SSE failures", ["route"])
SSE_PARTIAL_STREAM_TOTAL = Counter(
    "sse_partial_stream_total", "Number of partial SSE streams", ["route"]
)
SSE_RETRY_TOTAL = Counter("sse_retry_total", "Number of SSE retries", ["route"])
API_RETRY_TOTAL = Counter("api_retry_total", "Number of HTTP API retries", ["route"])
API_RETRY_SUCCESS_RATIO = Histogram(
    "api_retry_success_ratio", "Success ratio of API retries"
)

# Telemetry and request metrics for Phase 4
try:
    ASK_STREAM_REQUESTS_TOTAL = Counter(
        "gesahni_ask_stream_requests_total",
        "Count of streaming vs non-streaming requests",
        ["stream", "endpoint"]
    )
except Exception:  # pragma: no cover
    class _CStream:
        def labels(self, *a, **k):
            return self
        def inc(self, *a, **k):
            return None
    ASK_STREAM_REQUESTS_TOTAL = _CStream()  # type: ignore

try:
    ASK_TOKENS_EST_TOTAL = Counter(
        "gesahni_ask_tokens_est_total",
        "Count of requests by token estimation ranges",
        ["range", "endpoint"]
    )
except Exception:  # pragma: no cover
    class _CTokens:
        def labels(self, *a, **k):
            return self
        def inc(self, *a, **k):
            return None
    ASK_TOKENS_EST_TOTAL = _CTokens()  # type: ignore

try:
    ASK_ERROR_CODES_TOTAL = Counter(
        "gesahni_ask_error_codes_total",
        "Count of requests by error codes",
        ["error_code", "error_type", "endpoint"]
    )
except Exception:  # pragma: no cover
    class _CError:
        def labels(self, *a, **k):
            return self
        def inc(self, *a, **k):
            return None
    ASK_ERROR_CODES_TOTAL = _CError()  # type: ignore
