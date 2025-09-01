"""Constants for Google integration errors and metrics."""
ERR_OAUTH_EXCHANGE_FAILED = "oauth_exchange_failed"
ERR_OAUTH_INVALID_GRANT = "oauth_invalid_grant"

# Metric names (canonical) - integration layer should emit these
METRIC_TOKEN_EXCHANGE_FAILED = "google_token_exchange_failed_total"
METRIC_TOKEN_EXCHANGE_OK = "google_token_exchange_ok_total"



