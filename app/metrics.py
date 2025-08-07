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
    ["endpoint", "method", "engine"],
)

# Counter for LLaMA prompt/completion tokens
LLAMA_TOKENS = Counter("llama_tokens", "Number of LLaMA tokens", ["direction"])

# Histogram for LLaMA call latency in milliseconds
LLAMA_LATENCY = Histogram(
    "llama_latency_ms",
    "Latency of LLaMA generations in milliseconds",
)

# Counter for user memory additions
USER_MEMORY_ADDS = Counter(
    "user_memory_add_total",
    "Number of user memories added",
    ["store", "user"],
)
