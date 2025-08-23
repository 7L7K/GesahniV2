#!/bin/bash

# Test script for Gesahni monitoring dashboard
# Run this while viewing the Grafana dashboard to see metrics in action

echo "=== Gesahni Dashboard Testing Script ==="
echo "Run this script while viewing: http://localhost:3001"
echo ""

# Function to make requests and show what should happen in the dashboard
make_request() {
    local endpoint=$1
    local description=$2
    echo "→ $description"
    echo "   curl http://localhost:8000$endpoint"
    curl -s "http://localhost:8000$endpoint" > /dev/null
    echo "   ✓ Request completed"
    echo ""
}

# Test basic health endpoint (should show up in requests per route)
echo "1. Testing health endpoint (creates traffic in 'Requests per route' panel)"
make_request "/healthz" "Health check - generates basic traffic"

# Test 404 error (should show up in error ratio panel)
echo "2. Testing 404 error (should increase error ratio)"
make_request "/unknown-endpoint-404" "Non-existent endpoint - generates 404 error"

# Test 500 error if we can trigger one
echo "3. Testing error handling (if auth is enabled, this might trigger auth errors)"
make_request "/v1/csrf" "CSRF endpoint without auth - may trigger auth failure"

# Generate some load to see rate limiting if it kicks in
echo "4. Generating load (10 concurrent requests)"
echo "   → Load test - should show up in 'Requests per route' panel"
for i in {1..10}; do
    curl -s "http://localhost:8000/healthz" > /dev/null &
done
wait
echo "   ✓ Load test completed"
echo ""

# Check if metrics are being collected
echo "5. Verifying metrics collection"
echo "   → Checking if Prometheus can scrape metrics"
curl -s "http://localhost:8000/metrics" | grep -q "http_requests_total"
if [ $? -eq 0 ]; then
    echo "   ✓ Metrics endpoint is working"
else
    echo "   ✗ Metrics endpoint not responding"
fi
echo ""

echo "=== Dashboard Testing Complete ==="
echo "Check these panels in Grafana:"
echo "• Requests per route (5m) - should show traffic"
echo "• Error ratio (5xx) - should show error spikes"
echo "• Latency p50/p95/p99 - should show response times"
echo "• Auth failures by reason - may show failures if auth is enabled"
echo ""
echo "If you don't see data:"
echo "1. Verify Gesahni app is running on port 8000"
echo "2. Check Prometheus targets: http://localhost:9090/targets"
echo "3. Check Grafana data source: http://localhost:3001/datasources"
