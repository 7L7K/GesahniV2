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

# Counter for total number of requests
REQUEST_COUNT = Counter(
    "app_request_total", "Total number of requests", ["endpoint", "method", "engine"]
)

# Histogram for request latency in seconds
REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds",
    "Request latency in seconds",
    ["endpoint", "method", "engine"],
)

# New canonical names expected by dashboards/tests (do not remove legacy above)
try:
    GESAHNI_REQUESTS_TOTAL = Counter(
        "gesahni_requests_total",
        "Total HTTP requests",
        ["route", "method", "status"],
    )
except Exception:  # pragma: no cover - metrics optional
    class _C:
        def labels(self, *a, **k):
            return self
        def inc(self, *a, **k):
            return None
    GESAHNI_REQUESTS_TOTAL = _C()  # type: ignore

try:
    GESAHNI_LATENCY_SECONDS = Histogram(
        "gesahni_latency_seconds",
        "HTTP request latency in seconds",
        ["route"],
    )
except Exception:  # pragma: no cover
    class _H:
        def labels(self, *a, **k):
            return self
        def observe(self, *a, **k):
            return None
    GESAHNI_LATENCY_SECONDS = _H()  # type: ignore

# Health probe metrics ---------------------------------------------------------
try:
    HEALTH_CHECK_DURATION_SECONDS = Histogram(
        "gesahni_health_check_duration_seconds",
        "Health check duration (seconds)",
        ["check"],
    )
except Exception:  # pragma: no cover
    class _H2:
        def labels(self, *a, **k):
            return self
        def observe(self, *a, **k):
            return None
    HEALTH_CHECK_DURATION_SECONDS = _H2()  # type: ignore

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
AUTH_4XX_TOTAL = Counter(
    "auth_4xx_total", "Total 4xx auth failures", ["route", "code"]
)
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
ROUTER_DECISION = Counter(
    "router_decision_total", "Routing decisions made", ["rule"]
)

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
HEARTBEAT_OK = Counter(
    "care_heartbeat_ok_total", "Number of on-time device heartbeats"
)
HEARTBEAT_LATE = Counter(
    "care_heartbeat_late_total", "Number of late/missed device heartbeats"
)

# Care SMS queue metrics
CARE_SMS_RETRIES = Counter(
    "care_sms_retries_total", "Number of SMS retry attempts"
)
CARE_SMS_DLQ = Counter(
    "care_sms_dead_letter_total", "Number of SMS jobs sent to dead-letter queue"
)

# ----------------------------
# Rate limit metrics
# ----------------------------

RATE_LIMIT_ALLOWS = Counter(
    "rate_limit_allow_total",
    "Requests allowed by the rate limiter",
    ["channel", "bucket", "backend"],  # channel: http|ws; bucket: burst|long|daily|bypass
)

RATE_LIMIT_BLOCKS = Counter(
    "rate_limit_block_total",
    "Requests blocked by the rate limiter",
    ["channel", "bucket", "backend"],
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
SSE_FAIL_TOTAL = Counter(
    "sse_fail_total", "Number of SSE failures", ["route"]
)
SSE_PARTIAL_STREAM_TOTAL = Counter(
    "sse_partial_stream_total", "Number of partial SSE streams", ["route"]
)
SSE_RETRY_TOTAL = Counter(
    "sse_retry_total", "Number of SSE retries", ["route"]
)
API_RETRY_TOTAL = Counter(
    "api_retry_total", "Number of HTTP API retries", ["route"]
)
API_RETRY_SUCCESS_RATIO = Histogram(
    "api_retry_success_ratio", "Success ratio of API retries"
)
