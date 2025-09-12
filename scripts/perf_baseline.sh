#!/usr/bin/env bash
set -euo pipefail

# Performance Baseline Testing Script
# Tests key endpoints with hey load testing tool

echo "🚀 Running Performance Baseline Tests"
echo "===================================="

# Configuration
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
CONCURRENCY="${CONCURRENCY:-10}"
DURATION="${DURATION:-30s}"
OUTPUT_DIR="${OUTPUT_DIR:-perf_results}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Create output directory
mkdir -p "$OUTPUT_DIR"

echo "📊 Configuration:"
echo "  - Base URL: $BASE_URL"
echo "  - Concurrency: $CONCURRENCY"
echo "  - Duration: $DURATION"
echo "  - Output Directory: $OUTPUT_DIR"
echo ""

# Test endpoints
ENDPOINTS=(
    "/v1/healthz/live"
    "/v1/whoami"
    "/v1/auth/login"
    "/v1/music/command"
)

# Check if server is running
echo "🔍 Checking server availability..."
if ! curl -s --max-time 5 "$BASE_URL/v1/healthz/live" >/dev/null 2>&1; then
    echo "❌ Server not responding at $BASE_URL"
    echo "💡 Make sure the backend server is running:"
    echo "   cd /path/to/gesahni && ./scripts/backend-only.sh"
    exit 1
fi
echo "✅ Server is responding"

# Function to run hey test
run_hey_test() {
    local endpoint="$1"
    local output_file="$2"

    echo "🔬 Testing $endpoint..."

    # Different request methods/data for different endpoints
    case "$endpoint" in
        "/v1/auth/login")
            # POST request with JSON payload for login
            hey -n 1000 -c "$CONCURRENCY" -m POST \
                -H "Content-Type: application/json" \
                -d '{"username":"test","password":"test"}' \
                -o csv \
                "$BASE_URL$endpoint" > "$output_file"
            ;;
        "/v1/music/command")
            # POST request for music command
            hey -n 1000 -c "$CONCURRENCY" -m POST \
                -H "Content-Type: application/json" \
                -d '{"command":"play"}' \
                -o csv \
                "$BASE_URL$endpoint" > "$output_file"
            ;;
        *)
            # GET request for other endpoints
            hey -n 1000 -c "$CONCURRENCY" -m GET \
                -o csv \
                "$BASE_URL$endpoint" > "$output_file"
            ;;
    esac

    echo "✅ Test completed for $endpoint"
}

# Run tests for all endpoints
for endpoint in "${ENDPOINTS[@]}"; do
    # Sanitize endpoint name for filename
    filename=$(echo "$endpoint" | sed 's|/|_|g' | sed 's|^_||')
    output_file="$OUTPUT_DIR/${filename}_${TIMESTAMP}.csv"

    if run_hey_test "$endpoint" "$output_file"; then
        echo "📊 Results saved to $output_file"
    else
        echo "❌ Test failed for $endpoint"
    fi
    echo ""
done

# Generate summary report
echo "📋 Generating summary report..."
SUMMARY_FILE="$OUTPUT_DIR/summary_${TIMESTAMP}.txt"

{
    echo "Performance Baseline Report"
    echo "=========================="
    echo "Timestamp: $(date)"
    echo "Base URL: $BASE_URL"
    echo "Concurrency: $CONCURRENCY"
    echo "Test Duration: $DURATION"
    echo ""

    for endpoint in "${ENDPOINTS[@]}"; do
        filename=$(echo "$endpoint" | sed 's|/|_|g' | sed 's|^_||')
        csv_file="$OUTPUT_DIR/${filename}_${TIMESTAMP}.csv"

        if [[ -f "$csv_file" ]]; then
            echo "Endpoint: $endpoint"
            echo "Results file: $csv_file"

            # Extract key metrics from CSV (assuming hey CSV format)
            # Skip header line and get last line (summary)
            if [[ -s "$csv_file" ]]; then
                tail -n 1 "$csv_file" | awk -F',' '{
                    print "  Response time avg: " $2 "ms"
                    print "  Response time min: " $3 "ms"
                    print "  Response time max: " $4 "ms"
                    print "  Response time p50: " $5 "ms"
                    print "  Response time p95: " $6 "ms"
                    print "  Response time p99: " $7 "ms"
                }' 2>/dev/null || echo "  Could not parse CSV results"
            fi
            echo ""
        fi
    done
} > "$SUMMARY_FILE"

echo "📊 Summary report saved to $SUMMARY_FILE"
echo ""
echo "🎉 Performance baseline testing completed!"
echo "📁 Results available in: $OUTPUT_DIR"
