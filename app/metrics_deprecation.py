"""Prometheus metrics for tracking deprecated imports and usage."""

from prometheus_client import Counter, Histogram

# Track deprecated imports by module and symbol
DEPRECATED_IMPORTS = Counter(
    "deprecated_imports_total",
    "Total number of deprecated imports accessed",
    ["module", "symbol", "call_type"]
)

# Track deprecated import latency (how long it takes to access)
DEPRECATED_IMPORT_LATENCY = Histogram(
    "deprecated_import_latency_seconds",
    "Time spent accessing deprecated imports",
    ["module", "symbol"]
)

# Track whoami requests by source
WHOAMI_REQUESTS = Counter(
    "whoami_requests_total",
    "Total whoami requests by source",
    ["source", "jwt_status", "authenticated"]
)

# Track whoami latency
WHOAMI_LATENCY = Histogram(
    "whoami_latency_seconds",
    "Time spent processing whoami requests",
    ["source", "jwt_status"]
)
