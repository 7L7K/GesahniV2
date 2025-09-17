# Gesahni Monitoring Stack

This directory contains a Docker Compose setup for monitoring Gesahni with Prometheus and Grafana.

## Quick Start

1. **Start the monitoring stack:**
   ```bash
   docker compose -f monitoring/docker-compose.yml up -d
   ```

2. **Verify Prometheus is running:**
   - Open http://localhost:9090
   - Go to Status > Targets - should show `gesahni` as UP
   - Go to Graph tab and query: `http_requests_total`

3. **Access Grafana:**
   - Open http://localhost:3001
   - Anonymous access is enabled for Viewer role

4. **Test metrics:**
   - Query `job:http_requests:rate5m` to verify recording rules work
   - Query `job:request_latency_ms:p95` to verify latency metrics

5. **Check alerts:**
   - In Prometheus, go to Alerts tab to see configured alerts
   - Initially they should be inactive (green)

## Configuration Notes

- **Network**: Uses `host.docker.internal:8000` for macOS/Windows
- **For Linux**: Change to your host IP or container network
- **Retention**: Prometheus data retained for 15 days
- **Scrape interval**: 15 seconds (global)
- **Recording rules**: Evaluated every 30 seconds
- **Alertmanager**: Routes alerts to Slack channels by severity

## Alertmanager Setup

The monitoring stack includes Alertmanager for handling alerts and routing them to Slack.

### Slack Configuration

1. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

2. **Get Slack webhook URL:**
   - Go to https://api.slack.com/apps
   - Create a new app or use existing one
   - Enable "Incoming Webhooks"
   - Copy the webhook URL

3. **Configure webhook:**
   - Edit `.env` file
   - Set `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`

4. **Restart services:**
   ```bash
   docker compose -f monitoring/docker-compose.yml down
   docker compose -f monitoring/docker-compose.yml up -d
   ```

### Alert Routing

Alerts are routed by severity:
- **page** → `#oncall` channel (critical alerts)
- **ticket** → `#ops` channel (warning alerts)
- **info** → `#ops` channel (informational alerts)

### Testing Alerts

Use the provided test script to verify alert functionality:

```bash
./test-alerts.sh
```

This will:
- Generate normal traffic
- Create error conditions to trigger alerts
- Test auth failure scenarios

### Alertmanager UI

Access Alertmanager at http://localhost:9093 to:
- View active alerts
- Create silences
- Manage alert routing
- Test notification delivery

## SLO Implementation

The monitoring stack includes Service Level Objective (SLO) tracking with burn-rate alerts.

### Availability SLO
- **Target**: 99.5% success rate (non-5xx) over 30 days
- **Indicator**: `job:http_success_ratio:rate5m`
- **Formula**: `1 - (5xx_requests / total_requests)`

### Burn-Rate Alerts

Using Google's multi-window burn-rate method:

#### SLOFastBurn (Page Severity)
- **Window**: 5 minutes
- **Multiplier**: 14.4x (exhausts ~7.2% of monthly error budget)
- **Use Case**: Fast error rate increases requiring immediate action

#### SLOSlowBurn (Ticket Severity)
- **Window**: 1 hour
- **Multiplier**: 1.2x (exhausts ~0.6% of monthly error budget)
- **Use Case**: Sustained error rates threatening SLO over longer periods

### Testing SLO Alerts

```bash
./test-slo.sh
```

This will:
- Generate normal traffic (no alerts)
- Create fast burn scenario (SLOFastBurn alert)
- Create slow burn scenario (SLOSlowBurn alert)
- Provide monitoring instructions

## CI Validation

The monitoring stack includes automated validation to ensure configuration integrity.

### Makefile Targets

```bash
# Run all validations
make -C monitoring validate

# Individual validations
make -C monitoring validate-config    # Prometheus config syntax
make -C monitoring validate-rules     # Recording/alert rules syntax
make -C monitoring validate-metrics   # /metrics endpoint availability
make -C monitoring validate-all       # All validations + Alertmanager
```

### CI Integration

Add to your CI pipeline:

```yaml
# Example GitHub Actions step
- name: Validate Monitoring Configuration
  run: |
    # Start Gesahni app in background
    uvicorn app.main:app --host 127.0.0.1 --port 8000 &
    sleep 10  # Wait for app to start

    # Run monitoring validations
    make -C monitoring validate

    # Clean up
    pkill -f uvicorn
```

### Validation Checks

1. **Prometheus Config**: `promtool check config`
2. **Rules Syntax**: `promtool check rules`
3. **Metrics Endpoint**: `curl -sf http://localhost:8000/metrics`
4. **Alertmanager Config**: Docker-based validation

## Music Observability Dashboard

A specialized dashboard for monitoring Spotify integration and music functionality has been added.

### Accessing the Music Dashboard

1. **Grafana Dashboard**: Import `monitoring/grafana/dashboards/music-observability.json`
2. **Web UI**: Visit `/admin/metrics/music` in your Gesahni app for a simplified view
3. **Direct Link**: Navigate to "🎵 Music Dashboard" from the main admin metrics page

### Music Metrics Available

**Core Functionality:**
- `spotify_devices_request_count_total` - Device API requests by status and auth state
- `spotify_status_requests_count_total` - Status endpoint requests by status and auth state
- `spotify_devices_cache_bypass_count_total` - Cache bypass events
- `music_command_total` - Music control commands (play/pause/next/volume) by command, status, provider
- `music_state_request_total` - Music state requests with cache hit/miss tracking
- `music_set_device_total` - Set music device requests
- `tv_music_play_total` - TV music play requests

**WebSocket Activity:**
- `ws_music_connections_total` - WebSocket connections (connect/disconnect)
- `ws_music_messages_total` - WebSocket messages by direction and type

**Performance:**
- `music_cmd_latency_ms` - Legacy command latency percentiles
- `music_command_latency_seconds` - New command execution latency by command and provider
- `music_first_sound_ms` - Time to first audible sound
- `spotify_play_count_total` - Play request counts

**Error Tracking:**
- `music_transfer_fail_total` - Playback transfer failures
- `music_rate_limited_total` - Rate limiting events by provider

**Cache Performance:**
- `music_reco_hit_total` - Recommendation cache hits by vibe
- `music_reco_miss_total` - Recommendation cache misses by vibe

### Frontend Console Logging

The music hooks now log poll lifecycle events:
```javascript
console.info("music.poll:start", { pollMs, timestamp, hook: "useSpotifyStatus" });
console.info("music.poll:stop", { reason: "connected", pollCount, timestamp, hook: "useSpotifyStatus" });
```

## Files

- `docker-compose.yml` - Services configuration
- `prometheus/prometheus.yml` - Scrape configuration
- `prometheus/recording_rules.yml` - Metric rollups for performance + SLO success ratio
- `prometheus/alert_rules.yml` - Alert definitions + SLO burn-rate alerts
- `alertmanager/alertmanager.yml` - Alertmanager configuration with Slack routing
- `grafana/dashboards/service-overview.json` - General Grafana dashboard
- `grafana/dashboards/music-observability.json` - Music-specific dashboard
- `grafana/provisioning/` - Grafana auto-configuration
- `.env.example` - Slack webhook configuration template
- `Makefile` - CI validation commands
- `test-dashboard.sh` - Dashboard testing script
- `test-alerts.sh` - Alert testing script
- `test-slo.sh` - SLO burn-rate alert testing script

## Troubleshooting

1. **Target shows DOWN**: Check if Gesahni app is running on port 8000
2. **No metrics**: Verify `/metrics` endpoint is accessible
3. **Recording rules not working**: Check Prometheus logs for YAML syntax errors
4. **Alerts not firing**: Check alert rule syntax and thresholds
5. **Slack notifications not working**:
   - Verify `SLACK_WEBHOOK_URL` environment variable is set
   - Check Alertmanager logs for webhook errors
   - Test webhook URL directly with curl
6. **Alertmanager UI not accessible**: Check if service is running and port 9093 is not blocked
7. **SLO alerts not firing**: Check `job:http_success_ratio:rate5m` metric and ensure error rate exceeds thresholds
8. **CI validation fails**: Ensure `promtool` is installed and Gesahni app is running on port 8000
9. **Makefile errors**: Install `promtool` from Prometheus project and ensure curl is available

## Label Hygiene & Cardinality Management

The monitoring stack includes built-in label hygiene to prevent Prometheus cardinality explosion.

### Normalization Functions

**Model Labels:**
- `normalize_model_label(model)` - Maps model names to categories
  - `gpt-4o`, `gpt-4-turbo` → `"gpt4"`
  - `llama3:8b`, `llama2:7b` → `"llama3"`, `"llama2"`
  - Unknown models → hashed fallback

**Shape Labels:**
- `normalize_shape_label(shape)` - Categorizes request shapes
  - Chat completions → `"chat_completion"`
  - Embeddings → `"embedding"`
  - Unknown shapes → length-based categories

### Cardinality Monitoring

```bash
./cardinality_monitor.sh
```

This script helps identify potential cardinality issues:
- Checks high-risk label combinations
- Provides manual investigation steps
- Shows best practices for label usage

### Label Guidelines

**✅ Safe Labels:**
- `route`: Templated paths (e.g., `/v1/csrf`, not `/v1/csrf/123`)
- `method`: HTTP methods (GET, POST, PUT, DELETE)
- `status`: HTTP status codes (200, 404, 500)
- `scope`: Bounded permission scopes
- `reason`: Bounded error/failure reasons

**❌ Avoid These Labels:**
- `user_id`: Use hashed version instead
- `session_id`: Too unique, unbounded
- `request_id`: Unbounded, unique per request
- `ip_address`: PII and potentially unbounded
- Raw model names: Use normalized categories
- Timestamps: Use time ranges instead

### Metrics Audit

All metrics have been audited for cardinality issues:
- **ROUTER_REQUESTS_TOTAL**: Now uses normalized model labels
- **TTS_REQUEST_COUNT**: Uses normalized model/voice labels
- **ROUTER_SHAPE_NORMALIZED_TOTAL**: Uses categorized shape labels
- **USER_MEMORY_ADDS**: Already uses hashed user IDs

## Next Steps

1. Import Grafana dashboards from the main repo
2. Configure Alertmanager for notifications
3. Monitor cardinality growth regularly
4. Add more specific alerts based on your SLOs
