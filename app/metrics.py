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

# Histogram for request cost in USD
REQUEST_COST = Histogram(
    "app_request_cost_usd",
    "Request cost in USD",
    ["endpoint", "method", "engine", "segment"],
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
