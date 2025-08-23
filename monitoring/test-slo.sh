#!/bin/bash

# Test script for SLO burn-rate alerts
# This generates specific error patterns to trigger SLO alerts

echo "=== SLO Burn-Rate Alert Testing ==="
echo "Testing 99.5% availability SLO with multi-window burn-rate alerts"
echo ""

# Check if monitoring stack is running
if ! docker compose -f docker-compose.yml ps | grep -q "Up"; then
    echo "❌ Monitoring stack is not running!"
    echo "Start it first: docker compose -f docker-compose.yml up -d"
    exit 1
fi

echo "✅ Monitoring stack is running"
echo ""

# Function to generate errors
generate_errors() {
    local count=$1
    local message=$2
    echo "Generating $count errors: $message"

    for i in {1..$count}; do
        # Generate 500 errors by hitting a non-existent endpoint with special header
        curl -s -H "X-Test-Error: 500" "http://localhost:8000/unknown-endpoint-slo-test-$(date +%s)-$i" > /dev/null &
    done
    wait
}

# Function to generate successful requests
generate_success() {
    local count=$1
    local message=$2
    echo "Generating $count successful requests: $message"

    for i in {1..$count}; do
        curl -s "http://localhost:8000/healthz" > /dev/null &
    done
    wait
}

echo "📊 SLO Configuration:"
echo "   Target: 99.5% success rate over 30 days"
echo "   Fast burn alert: >14.4x normal error rate (5min window)"
echo "   Slow burn alert: >1.2x normal error rate (1hour window)"
echo ""

echo "🔍 Current success ratio (should be ~1.0):"
echo "   Query in Prometheus: job:http_success_ratio:rate5m"
echo ""

# Scenario 1: Normal operation (should not trigger alerts)
echo "1. 🟢 Testing normal operation (should NOT trigger alerts)"
generate_success 50 "Normal traffic generation"
echo "   ✅ Normal traffic generated - alerts should remain inactive"
echo ""

# Scenario 2: Fast burn test - generate high error rate quickly
echo "2. 🔴 Testing FAST BURN scenario (should trigger SLOFastBurn alert)"
echo "   Generating high error rate to exceed 14.4x multiplier..."
generate_errors 100 "Fast burn error generation"
echo "   ✅ Fast burn errors generated - check for 'SLOFastBurn' alert"
echo ""

# Wait a bit for metrics to propagate
echo "   Waiting 30 seconds for metrics to propagate..."
sleep 30

# Scenario 3: Slow burn test - generate moderate error rate over time
echo "3. 🟡 Testing SLOW BURN scenario (should trigger SLOSlowBurn alert)"
echo "   Generating sustained moderate error rate..."
for i in {1..3}; do
    echo "   Round $i/3: Generating 20 errors with 10 success requests..."
    generate_errors 20 "Slow burn round $i"
    generate_success 10 "Slow burn success round $i"
    echo "   Waiting 30 seconds between rounds..."
    sleep 30
done
echo "   ✅ Slow burn errors generated - check for 'SLOSlowBurn' alert"
echo ""

echo "📈 Monitoring Instructions:"
echo ""
echo "1. **Prometheus** (http://localhost:9090):"
echo "   - Go to Alerts tab"
echo "   - Look for 'SLOFastBurn' (page severity) and 'SLOSlowBurn' (ticket severity)"
echo "   - Check 'job:http_success_ratio:rate5m' metric"
echo ""
echo "2. **Alertmanager** (http://localhost:9093):"
echo "   - View received alerts"
echo "   - Check alert routing to Slack channels"
echo ""
echo "3. **Grafana** (http://localhost:3001):"
echo "   - View the 'Error ratio (5xx)' panel"
echo "   - Should show error spikes during testing"
echo ""

echo "🧮 SLO Burn-Rate Calculations:"
echo ""
echo "Fast Burn (14.4x multiplier):"
echo "   - Target: 99.5% = 0.995 success ratio"
echo "   - Error budget: 1 - 0.995 = 0.005"
echo "   - Fast burn threshold: 0.005 * 14.4 = 0.072 (7.2% error rate)"
echo ""
echo "Slow Burn (1.2x multiplier):"
echo "   - Target: 99.5% = 0.995 success ratio"
echo "   - Error budget: 1 - 0.995 = 0.005"
echo "   - Slow burn threshold: 0.005 * 1.2 = 0.006 (0.6% error rate)"
echo ""

echo "⚠️  Alert Thresholds:"
echo "   - SLOFastBurn: Success ratio < 0.928 (error rate >7.2%) for 5 minutes"
echo "   - SLOSlowBurn: Success ratio < 0.994 (error rate >0.6%) for 1 hour"
echo ""
echo "💡 Tip: The alerts use Google's multi-window burn-rate method to detect"
echo "   different rates of error budget consumption over different time windows."
echo ""

echo "✅ SLO testing complete!"
echo "Monitor the URLs above to see SLO alerts in action."
