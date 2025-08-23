#!/usr/bin/env bash
set -euo pipefail

echo "=== Gesahni Monitoring One-Shot Smoke Verification ==="

# 1) Baseline requests
echo "1) Sending baseline requests to /health"
for i in {1..10}; do
  curl -sS --retry 2 --retry-delay 1 http://127.0.0.1:8000/health >/dev/null || true
done

echo "Baseline requests sent."

# 2) Induce some 404s
echo "2) Inducing 404s"
for i in {1..10}; do
  curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/nope-$i || true
done

echo "404 induction complete."

# 3) Metrics sanity
echo "3) Metrics sanity check (showing http_requests_total help & sample lines)"
if command -v rg >/dev/null 2>&1; then
  curl -s http://127.0.0.1:8000/metrics | rg -e '^# HELP http_requests_total' -e '^http_requests_total' | head -n 20 || true
else
  curl -s http://127.0.0.1:8000/metrics | grep -E '^# HELP http_requests_total|^http_requests_total' | head -n 20 || true
fi

echo "\n4) Manual Prometheus queries to check in UI:"
echo "  - job:http_requests:rate5m"
echo "  - job:http_requests_error_ratio:rate5m"
echo "  - job:request_latency_ms:p95"
echo "  - job:auth_fail:rate5m"
echo "  - job:rbac_deny:rate5m"
echo "  - job:rate_limited:rate5m"

echo "\nPhase 7 DoD checklist (manual verification where noted):"
echo "- Prometheus target UP: http://localhost:9090 -> Status > Targets"
echo "- Recording rules present and queryable: job:http_requests:rate5m, job:http_requests_error_ratio:rate5m, job:request_latency_ms:p50/p95/p99"
echo "- Grafana dashboard loads and panels render: http://localhost:3001"
echo "- Alerts: force condition and check Alertmanager UI http://localhost:9093 and Slack"
echo "- SLO burn-rate alerts configured: check alert_rules.yml"
echo "- CI validation: make -C monitoring validate"
echo "- Label hygiene: no PII; stable route labels"

echo "\nSmoke verification script complete."
