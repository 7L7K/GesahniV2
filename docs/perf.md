Performance and Load Testing

## k6

- Install: `brew install k6`
- Run smoke: `BASE_URL=http://localhost:8000 k6 run perf/k6/smoke.js`
- Env:
  - `K6_VUS` (default 5)
  - `K6_DURATION` (default 1m)
  - Thresholds: p95 < 500ms, error rate < 1%

## Locust

- Install: `pip install locust`
- Run: `locust -f perf/locust/locustfile.py --host=http://localhost:8000`
- Env:
  - `LOCUST_SLO_P95_MS` (default 500)

## Metrics and Dashboard

Export `/metrics` (Prometheus). The app exposes:
- app_request_total, app_request_latency_seconds, app_request_cost_usd
- model_latency_seconds, llama_latency_ms
- vector_selected_total, vector_init_fallbacks_total, vector_fallback_reads_total
- rate_limit_allow_total, rate_limit_block_total

A sample Grafana dashboard is in `grafana_dashboard.json`.

