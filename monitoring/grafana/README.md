# Gesahni Grafana Dashboards

This directory contains Grafana configuration and dashboards for monitoring Gesahni.

## Dashboard Overview

The **"Gesahni — Service Overview"** dashboard includes these panels:

### Main Panels
- **Requests per route (5m)**: `job:http_requests:rate5m`
  - Shows request rates by route and method
  - Legend: `{{route}} {{method}} rps`

- **Error ratio (5xx)**: `job:http_requests_error_ratio:rate5m`
  - 5xx error ratio with color-coded thresholds
  - Warning: 2%, Critical: 5%

- **Latency p50/p95/p99 (ms)**: `job:request_latency_ms:p50/p95/p99`
  - Three separate time series for different percentiles
  - Color-coded thresholds at 1s (warning) and 2s (critical)

### Security & Access Control
- **Auth failures by reason**: `job:auth_fail:rate5m`
  - Auth failures broken down by failure reason
  - Legend: `{{reason}}`

- **RBAC denies by scope**: `job:rbac_deny:rate5m`
  - Authorization denials by scope
  - Legend: `{{scope}}`

### System Health
- **Rate limited (per 5m)**: `job:rate_limited:rate5m`
  - Requests being rate limited

- **LLaMA queue depth**: `gesahni_llama_queue_depth`
  - AI processing queue depth (if LLaMA is enabled)
  - Thresholds: warning at 5, critical at 10

## Setup Instructions

### Option 1: Automatic Setup (Recommended)
The Docker Compose setup includes automatic provisioning:

```bash
# Start monitoring stack
docker compose -f monitoring/docker-compose.yml up -d

# Access Grafana at http://localhost:3001
# Dashboard will be automatically imported and available
```

### Option 2: Manual Setup
If you prefer to manually configure Grafana:

1. **Add Prometheus Data Source**:
   - URL: `http://localhost:9090` (if running locally) or `http://prometheus:9090` (inside Docker network)
   - Access: Server (for Docker) or Browser (for local development)

2. **Import Dashboard**:
   - Go to Dashboards → New → Import
   - Upload `monitoring/grafana/dashboards/service-overview.json`
   - Select the Prometheus data source

## Testing the Dashboard

### Basic Health Check
```bash
# Hit the health endpoint to generate traffic
curl http://localhost:8000/healthz

# Hit a non-existent route to trigger 404s
curl http://localhost:8000/unknown-route
```

### Authentication Testing
```bash
# Test with invalid token (if auth is enabled)
curl -H "Authorization: Bearer invalid" http://localhost:8000/v1/csrf

# Test without token
curl http://localhost:8000/v1/csrf
```

### Load Testing
```bash
# Generate some load to see metrics in action
for i in {1..10}; do
  curl http://localhost:8000/healthz &
done
```

## Dashboard Features

- **Auto-refresh**: 30-second intervals
- **Time range**: Default 1 hour, customizable
- **Responsive layout**: 24-column grid with proper panel sizing
- **Color-coded thresholds**: Visual indicators for performance issues
- **Meaningful legends**: Clear identification of metrics by labels

## Customization

### Adding New Panels
1. Edit `monitoring/grafana/dashboards/service-overview.json`
2. Add new panel objects to the `panels` array
3. Update panel IDs and grid positions
4. Restart Grafana or re-import the dashboard

### Modifying Thresholds
- Warning thresholds: Orange (#EAB839)
- Critical thresholds: Red (#d44a3a)
- Edit the `thresholds.steps` array in panel configurations

## Troubleshooting

### No Data in Panels
- Verify Prometheus is scraping correctly: http://localhost:9090/targets
- Check that Gesahni app is running and accessible on port 8000
- Confirm `/metrics` endpoint returns data: http://localhost:8000/metrics

### Dashboard Not Loading
- Check Grafana logs: `docker compose logs grafana`
- Verify JSON syntax in dashboard file
- Ensure data source is properly configured

### Recording Rules Not Working
- Check Prometheus configuration includes the rule files
- Verify recording rules syntax: http://localhost:9090/rules
- Confirm metrics exist in Prometheus: http://localhost:9090/graph

## File Structure

```
monitoring/grafana/
├── dashboards/
│   └── service-overview.json    # Main dashboard
├── provisioning/
│   ├── dashboards/
│   │   └── gesahni-dashboards.yaml  # Dashboard provisioning
│   └── datasources/
│       └── prometheus.yaml          # Data source provisioning
└── README.md                       # This file
```
