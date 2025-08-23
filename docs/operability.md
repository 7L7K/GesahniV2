# Operability: SLIs & SLOs

## Overview

This document defines Service Level Indicators (SLIs) and Service Level Objectives (SLOs) for the Gesahni system. These targets are designed to be measurable and testable in CI/CD pipelines.

## 🎯 Service Level Objectives (SLOs)

### 1. Availability SLO
**Target**: 99.9% of GET /healthz responses return 200 over 30 days

**SLI**: Request Success Rate
```
Success Rate = (Total Successful Requests) / (Total Requests) * 100%
Where: Successful = HTTP 200-299 responses
```

**Measurement Window**: 30 days (rolling)

**Alert Thresholds**:
- **Warning**: < 99.5% (triggers investigation)
- **Critical**: < 99.0% (requires immediate action)

**Prometheus Query**:
```promql
# Availability over 30 days
sum(rate(http_requests_total{route="/healthz", method="GET", status="200"}[30d]))
/ sum(rate(http_requests_total{route="/healthz", method="GET"}[30d])) >= 0.999
```

### 2. Latency SLOs (P95)

#### Read Endpoints Latency
**Target**: P95 ≤ 250ms for all GET endpoints

**Included Endpoints**:
- `/v1/admin/*` (GET)
- `/v1/ask` (GET components)
- `/v1/healthz`
- `/v1/metrics`
- All other GET endpoints

**Prometheus Query**:
```promql
# P95 latency for GET requests
histogram_quantile(0.95, sum(rate(http_request_latency_seconds_bucket{method="GET"}[5m])) by (le)) <= 0.25
```

#### Write Endpoints Latency
**Target**: P95 ≤ 500ms for all write operations

**Included Operations**:
- POST, PUT, PATCH, DELETE methods
- WebSocket message processing
- File uploads
- Database operations

**Prometheus Query**:
```promql
# P95 latency for write operations
histogram_quantile(0.95, sum(rate(http_request_latency_seconds_bucket{method=~"POST|PUT|PATCH|DELETE"}[5m])) by (le)) <= 0.5
```

### 3. Error Budget SLOs

#### 4xx Error Rate (excluding auth failures)
**Target**: ≤ 0.5% of total requests return 4xx errors (excluding 401/403)

**Excluded Errors**:
- 401 Unauthorized (authentication required)
- 403 Forbidden (insufficient permissions)

**Included Errors**:
- 400 Bad Request (malformed requests)
- 404 Not Found
- 409 Conflict
- 422 Unprocessable Entity
- Other 4xx client errors

**Prometheus Query**:
```promql
# 4xx error rate (excluding auth)
sum(rate(http_requests_total{status=~"4..", status!~"401|403"}[5m]))
/ sum(rate(http_requests_total[5m])) <= 0.005
```

#### 5xx Error Rate
**Target**: ≤ 0.1% of total requests return 5xx errors

**Included Errors**:
- 500 Internal Server Error
- 502 Bad Gateway
- 503 Service Unavailable
- 504 Gateway Timeout
- All other 5xx server errors

**Prometheus Query**:
```promql
# 5xx error rate
sum(rate(http_requests_total{status=~"5.."}[5m]))
/ sum(rate(http_requests_total[5m])) <= 0.001
```

### 4. Rate Limit Budget
**Target**: ≤ 1% of requests hit 429 (rate limited) in normal operations

**Context**: Rate limiting should only trigger during:
- Abnormal usage patterns
- Attack attempts
- Misconfigured clients
- Not during normal peak usage

**Prometheus Query**:
```promql
# Rate limit percentage
sum(rate(http_requests_total{status="429"}[5m]))
/ sum(rate(http_requests_total[5m])) <= 0.01
```

## 📊 Alerting Expressions

### Critical Alerts (Immediate Action Required)

#### 1. 5xx Error Spike
```promql
# 5xx error rate > 0.5% (5x the SLO target)
sum(rate(http_requests_total{status=~"5.."}[5m]))
/ sum(rate(http_requests_total[5m])) > 0.005
```
**Action**: Immediate investigation, potential rollback, incident response

#### 2. Critical Latency Violation
```promql
# P95 latency > 1s on reads (4x the SLO target)
histogram_quantile(0.95, sum(rate(http_request_latency_seconds_bucket{method="GET"}[5m])) by (le)) > 1.0
```
**Action**: Performance optimization, potential scaling

#### 3. Availability Drop
```promql
# Health check availability < 99% over 1 hour
sum(rate(http_requests_total{route="/healthz", method="GET", status="200"}[1h]))
/ sum(rate(http_requests_total{route="/healthz", method="GET"}[1h])) < 0.99
```
**Action**: System health check, potential restart

### Warning Alerts (Investigation Required)

#### 4. 4xx Error Rate Warning
```promql
# 4xx error rate > 1% (2x the SLO target)
sum(rate(http_requests_total{status=~"4..", status!~"401|403"}[5m]))
/ sum(rate(http_requests_total[5m])) > 0.01
```
**Action**: Client integration review, API usage analysis

#### 5. Write Latency Warning
```promql
# P95 latency > 1s on writes (2x the SLO target)
histogram_quantile(0.95, sum(rate(http_request_latency_seconds_bucket{method=~"POST|PUT|PATCH|DELETE"}[5m])) by (le)) > 1.0
```
**Action**: Database performance check, optimization opportunity

#### 6. Rate Limit Warning
```promql
# Rate limit percentage > 2% (2x the SLO target)
sum(rate(http_requests_total{status="429"}[5m]))
/ sum(rate(http_requests_total[5m])) > 0.02
```
**Action**: Rate limit configuration review, usage pattern analysis

## 🧪 CI/CD Testing

### SLO Compliance Tests

#### 1. Synthetic Availability Test
```bash
# Run every 5 minutes in CI
for i in {1..100}; do
  if ! curl -f http://localhost:8000/healthz >/dev/null 2>&1; then
    echo "Health check failed (attempt $i)"
    exit 1
  fi
done
echo "✓ All health checks passed"
```

#### 2. Latency Benchmark Test
```bash
# Run during performance testing
ab -n 1000 -c 10 -g results.tsv http://localhost:8000/v1/admin/metrics

# Calculate P95 from results
p95=$(awk 'NR>1 {print $5}' results.tsv | sort -n | awk 'BEGIN{c=0} {a[c++]=$1} END{print a[int(c*0.95)]}')

if (( $(echo "$p95 > 0.25" | bc -l) )); then
  echo "❌ P95 latency $p95 > 250ms target"
  exit 1
else
  echo "✅ P95 latency $p95 <= 250ms target"
fi
```

#### 3. Error Rate Test
```bash
# After load testing
total_requests=$(grep -c "http_requests_total" metrics.out)
error_4xx=$(grep -c 'status="4.."' metrics.out)
error_5xx=$(grep -c 'status="5.."' metrics.out)

error_rate_4xx=$(echo "scale=4; $error_4xx / $total_requests" | bc)
error_rate_5xx=$(echo "scale=4; $error_5xx / $total_requests" | bc)

if (( $(echo "$error_rate_4xx > 0.005" | bc -l) )); then
  echo "❌ 4xx error rate $error_rate_4xx > 0.5% target"
  exit 1
fi

if (( $(echo "$error_rate_5xx > 0.001" | bc -l) )); then
  echo "❌ 5xx error rate $error_rate_5xx > 0.1% target"
  exit 1
fi

echo "✅ Error rates within SLO targets"
```

## 📈 Monitoring Dashboard

### Grafana Panels Recommended

#### 1. SLO Status Overview
- **Availability**: Current 30-day success rate for /healthz
- **Latency**: P95 for reads/writes over last hour
- **Error Rates**: 4xx/5xx rates over last hour
- **Rate Limits**: 429 percentage over last hour

#### 2. Error Budget Burn Rate
- **Daily Burn**: How fast you're consuming error budget
- **Weekly Projection**: Estimated time to exhaust budget
- **Monthly Trend**: Long-term error budget consumption

#### 3. Latency Distribution
- **Histogram**: Request latency distribution by endpoint
- **P50/P95/P99**: Percentile breakdown
- **Top Slow Endpoints**: Identify optimization targets

#### 4. Availability Timeline
- **Success Rate**: Rolling success rate over time
- **Outages**: Timeline of availability incidents
- **MTTR**: Mean time to recovery

## 🔧 Implementation Notes

### 1. Metrics Collection
Ensure all endpoints are instrumented with:
- `http_requests_total{route, method, status}`
- `http_request_latency_seconds{route, method}`

### 2. Alert Configuration
Configure alerts in your monitoring system:
- **Critical**: Page on-call engineer
- **Warning**: Create investigation ticket
- **Info**: Log for trend analysis

### 3. SLO Review Process
- **Monthly**: Review SLO achievement vs targets
- **Quarterly**: Adjust targets based on business needs
- **Incident Postmortem**: Update SLOs based on learnings

### 4. Error Budget Management
- **Track consumption**: Monitor how fast you're burning error budget
- **Plan releases**: Avoid deployments when budget is low
- **Quality gates**: Block deployments if error rates are too high

## 🎯 Success Criteria

### SLO Achievement
- ✅ **99.9% availability** for health checks
- ✅ **P95 ≤ 250ms** for read operations
- ✅ **P95 ≤ 500ms** for write operations
- ✅ **≤ 0.5% 4xx errors** (excluding auth)
- ✅ **≤ 0.1% 5xx errors**
- ✅ **≤ 1% rate limited** requests

### Monitoring Implementation
- ✅ **Prometheus metrics** properly configured
- ✅ **Alerting rules** defined and tested
- ✅ **Grafana dashboards** created
- ✅ **CI/CD integration** for SLO testing

### Operational Excellence
- ✅ **Error budget tracking** implemented
- ✅ **Incident response** processes defined
- ✅ **Postmortem reviews** include SLO analysis
- ✅ **Team accountability** for SLO achievement

## 🚀 Getting Started

1. **Implement metrics collection** for all endpoints
2. **Configure Prometheus alerting** with the expressions above
3. **Create Grafana dashboards** to visualize SLO status
4. **Set up CI/CD tests** to validate SLO compliance
5. **Establish processes** for error budget management

These SLOs provide concrete, measurable targets that ensure your system maintains high availability and performance while allowing for controlled error budgets and operational improvements.
