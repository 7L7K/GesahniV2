#!/bin/bash

# Cardinality monitoring script for Prometheus metrics
# Helps identify potential cardinality issues before they become problems

echo "=== Prometheus Cardinality Monitor ==="
echo ""

# Check if monitoring stack is running
if ! docker compose -f docker-compose.yml ps | grep -q "Up"; then
    echo "❌ Monitoring stack is not running!"
    echo "Start it first: docker compose -f docker-compose.yml up -d"
    exit 1
fi

echo "✅ Monitoring stack is running"
echo ""

# Function to check label cardinality
check_label_cardinality() {
    local metric=$1
    local label=$2
    local threshold=${3:-50}

    echo "🔍 Checking cardinality for $metric{$label}"
    echo "   Query: count_values(\"$label\", $metric)"
    echo ""

    # This would require curl to Prometheus API
    echo "   To check manually in Prometheus:"
    echo "   1. Go to http://localhost:9090"
    echo "   2. Query: count_values(\"$label\", $metric)"
    echo "   3. If result > $threshold, investigate!"
    echo ""
}

echo "📊 High-Risk Label Cardinality Checks:"
echo "======================================"
echo ""

# Check model labels (should be normalized)
check_label_cardinality "router_requests_total" "model" 10
check_label_cardinality "tts_request_total" "variant" 20

# Check shape labels (should be categorized)
check_label_cardinality "router_shape_normalized_total" "from_shape" 15
check_label_cardinality "router_shape_normalized_total" "to_shape" 15

# Check other potentially problematic labels
check_label_cardinality "user_memory_add_total" "user" 100  # Should be hashed

echo "🔧 Manual Cardinality Investigation:"
echo "==================================="
echo ""
echo "1. **Check top series by cardinality:**"
echo "   curl http://localhost:9090/api/v1/label/__name__/values"
echo ""
echo "2. **Check specific label values:**"
echo "   curl http://localhost:9090/api/v1/label/<label_name>/values"
echo ""
echo "3. **Check memory usage:**"
echo "   curl http://localhost:9090/status"
echo "   Look for 'head chunks' and 'num series'"
echo ""
echo "4. **Monitor series growth:**"
echo "   curl http://localhost:9090/api/v1/query?query=prometheus_build_info"
echo "   Check 'time series count' over time"
echo ""

echo "⚠️  Cardinality Best Practices:"
echo "=============================="
echo ""
echo "✅ DO use these labels:"
echo "   - route (templated, e.g., /v1/csrf, not /v1/csrf/123)"
echo "   - method (GET, POST, PUT, DELETE)"
echo "   - status (200, 404, 500)"
echo "   - scope (bounded permission set)"
echo "   - reason (bounded error/failure reasons)"
echo ""
echo "❌ DON'T use these as labels:"
echo "   - user_id (use hashed version)"
echo "   - session_id (too unique)"
echo "   - request_id (unbounded)"
echo "   - ip_address (PII and unbounded)"
echo "   - raw model names (use normalized categories)"
echo "   - timestamps (use time ranges instead)"
echo ""
echo "🛠️  Normalization Functions Available:"
echo "   - normalize_model_label(model) -> 'gpt4', 'llama3', etc."
echo "   - normalize_shape_label(shape) -> 'chat_completion', 'embedding', etc."
echo ""

echo "✅ Cardinality monitoring complete!"
