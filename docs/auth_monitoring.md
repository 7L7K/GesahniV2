# Authentication Monitoring

This document describes the structured logging and monitoring system for authentication events in GesahniV2.

## Overview

The authentication monitoring system provides comprehensive observability for authentication-related events with structured logs and Prometheus metrics for alerting and dashboard visualization.

## Structured Logs

### Auth Event Types

The system tracks the following authentication event types:

- `auth.finish.start/end` - Authentication finish process timing
- `auth.whoami.start/end` - Whoami endpoint call timing  
- `auth.lock.on/off` - Authentication lock events
- `auth.authed.change` - Authentication state changes

### Log Fields

Each authentication event includes structured fields:

```json
{
  "event": "auth_event",
  "event_type": "whoami.call",
  "user_id": "user123",
  "source": "cookie",
  "jwt_status": "ok",
  "session_ready": true,
  "is_authenticated": true,
  "lock_reason": "rate_limit",
  "boot_phase": false,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

## Prometheus Metrics

### Counters

- `whoami_calls_total{status, source, boot_phase}` - Total whoami endpoint calls
- `finish_calls_total{status, method, reason}` - Total auth finish endpoint calls
- `privileged_calls_blocked_total{endpoint, reason}` - Total blocked privileged calls
- `ws_reconnect_attempts_total{endpoint, reason}` - Total WebSocket reconnection attempts

### Histograms

- `auth_event_duration_seconds{event_type, status}` - Authentication event timing

## Dashboard Alerts

### Boot Phase Alerts

1. **Multiple whoami calls during boot**: Alert when more than 1 whoami call is detected within 2 seconds during the boot phase (first 30 seconds)

2. **401 errors during boot**: Alert when any 401 errors are detected from APIs during the boot phase

### Alert Configuration

The alerts are configured in the Grafana dashboard (`grafana_auth_dashboard.json`) with:

- **Thresholds**: 
  - Whoami calls: > 1 during boot phase
  - 401 errors: > 0 during boot phase
- **Frequency**: 1 minute evaluation
- **No Data State**: No data

## Implementation

### Core Components

1. **`app/auth_monitoring.py`** - Main monitoring module with logging and metrics functions
2. **`app/metrics.py`** - Prometheus metric definitions
3. **`app/telemetry.py`** - Extended LogRecord model with auth fields
4. **`app/api/auth.py`** - Integration with whoami and finish endpoints
5. **`app/security.py`** - Integration with authentication verification

### Usage Examples

```python
# Log an authentication event
from app.auth_monitoring import log_auth_event

log_auth_event(
    event_type="whoami.call",
    user_id="user123",
    source="cookie",
    jwt_status="ok",
    session_ready=True,
    is_authenticated=True
)

# Track event timing
from app.auth_monitoring import track_auth_event

with track_auth_event("whoami", user_id="user123"):
    # Authentication logic here
    pass

# Record specific events
from app.auth_monitoring import record_whoami_call

record_whoami_call(
    status="success",
    source="cookie",
    user_id="user123",
    session_ready=True,
    is_authenticated=True,
    jwt_status="ok"
)
```

## Configuration

### Environment Variables

- `PROMETHEUS_ENABLED=1` - Enable Prometheus metrics endpoint
- `AUTH_MONITORING_ENABLED=1` - Enable authentication monitoring (default: enabled)

### Boot Phase Detection

The system considers the first 30 seconds after application startup as the "boot phase" for alerting purposes. This can be configured by modifying the `_BOOT_PHASE_DURATION` constant in `auth_monitoring.py`.

## Dashboard Setup

1. Import the `grafana_auth_dashboard.json` into Grafana
2. Configure the Prometheus data source
3. Set up notification channels for alerts
4. Customize alert thresholds as needed

## Monitoring Best Practices

1. **Monitor boot phase closely** - Authentication issues during startup can indicate configuration problems
2. **Track 401 error patterns** - Sudden spikes may indicate token expiration or security issues
3. **Watch WebSocket reconnections** - Frequent reconnections may indicate network or authentication instability
4. **Monitor authentication success rates** - Should remain high (>99%) in normal operation

## Troubleshooting

### Common Issues

1. **High whoami call volume during boot**: Check for frontend authentication loops
2. **401 errors during boot**: Verify JWT configuration and token validity
3. **WebSocket reconnection loops**: Check authentication state management in frontend
4. **Missing metrics**: Ensure Prometheus is enabled and metrics endpoint is accessible

### Debug Logs

Enable debug logging for authentication monitoring:

```python
import logging
logging.getLogger('app.auth_monitoring').setLevel(logging.DEBUG)
```

## Integration with Existing Systems

The authentication monitoring integrates with:

- **Existing logging infrastructure** - Uses structured JSON logging
- **Prometheus metrics** - Extends existing metrics collection
- **Grafana dashboards** - Compatible with existing dashboard setup
- **Alerting systems** - Uses standard Grafana alerting

## Future Enhancements

Potential improvements:

1. **Authentication lock tracking** - Monitor rate limiting and lockout events
2. **Session analytics** - Track session duration and patterns
3. **Geographic tracking** - Monitor authentication by location
4. **Device fingerprinting** - Track authentication by device type
5. **Real-time alerts** - Webhook notifications for critical auth failures
