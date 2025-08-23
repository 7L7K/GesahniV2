#!/bin/bash

# Test script for Alertmanager and Slack alerting
# This script generates traffic that should trigger alerts

echo "=== Alertmanager Testing Script ==="
echo "This will generate traffic to trigger alerts"
echo ""

# Check if monitoring stack is running
if ! docker compose -f monitoring/docker-compose.yml ps | grep -q "Up"; then
    echo "❌ Monitoring stack is not running!"
    echo "Start it first: docker compose -f monitoring/docker-compose.yml up -d"
    exit 1
fi

echo "✅ Monitoring stack is running"
echo ""

# Function to make requests
make_request() {
    local endpoint=$1
    local count=${2:-1}
    for i in {1..$count}; do
        curl -s "http://localhost:8000$endpoint" > /dev/null &
    done
    wait
}

echo "📊 Testing different alert scenarios..."
echo ""

# Test 1: Generate normal traffic (should not trigger alerts)
echo "1. Generating normal traffic (/healthz x 10)"
make_request "/healthz" 10
echo "   ✅ Normal traffic generated"
echo ""

# Test 2: Generate 404 errors to test error ratio alert
echo "2. Generating 404 errors to trigger 'HighErrorRate5xx' alert"
echo "   Making 100 requests to non-existent endpoints..."
for i in {1..100}; do
    curl -s "http://localhost:8000/unknown-endpoint-$(date +%s)-$i" > /dev/null &
done
wait
echo "   ✅ 100 404 errors generated (should trigger alert when >5% error ratio)"
echo ""

# Test 3: Generate auth failures (if auth is enabled)
echo "3. Testing auth failures (may trigger 'AuthFailuresSpike' alert)"
curl -s -H "Authorization: Bearer invalid-token-$(date +%s)" "http://localhost:8000/v1/csrf" > /dev/null
echo "   ✅ Auth failure attempt made"
echo ""

echo "🔍 Check the following to verify alerts are working:"
echo ""
echo "1. Prometheus Alerts: http://localhost:9090/alerts"
echo "   - Should show alerts transitioning from 'pending' to 'firing'"
echo ""
echo "2. Alertmanager UI: http://localhost:9093"
echo "   - Should show received alerts"
echo "   - Click on alerts to see details"
echo ""
echo "3. Slack notifications (if SLACK_WEBHOOK_URL is configured)"
echo "   - Check #oncall channel for critical alerts"
echo "   - Check #ops channel for warning/info alerts"
echo ""

echo "🧪 Testing Alertmanager Silence/Resolve:"
echo ""
echo "In Alertmanager UI (http://localhost:9093):"
echo "1. Click on a firing alert"
echo "2. Click 'Silence' to create a silence"
echo "3. Fill in creator, comment, and duration"
echo "4. Click 'Create' to silence the alert"
echo "5. Verify alert shows as silenced in both Prometheus and Alertmanager"
echo ""
echo "6. To resolve: Wait for alert condition to clear, or delete silence"
echo ""

echo "⚠️  Note: Alert thresholds are configured as:"
echo "   - HighErrorRate5xx: >5% error ratio for 10 minutes"
echo "   - AuthFailuresSpike: >5 failures in 5 minutes"
echo "   - Other alerts have various thresholds"
echo ""
echo "It may take several minutes for alerts to fire due to the 'for' duration!"
echo ""

echo "✅ Alert testing complete!"
echo "Monitor the URLs above to see alerts in action."
