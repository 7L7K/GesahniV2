#!/bin/bash
set -e

# Synthetic smoke test for GesahniV2
# Tests 5 endpoints in under 5 seconds

base=${BASE:-http://localhost:8000}

echo "🚀 Running synthetic smoke test against $base"

# Function to check endpoint with expected status
check() {
    local url="$1"
    local expected_code="$2"
    local start_time=$(date +%s)
    local code=$(curl -s -o /dev/null -w "%{http_code}" "$base$url")
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))

    if [ "$code" = "$expected_code" ]; then
        echo "✅ $url -> $code"
    else
        echo "❌ $url -> $code (expected $expected_code)"
        exit 1
    fi
}

echo "Testing endpoints..."

# Test health endpoint
check /health 200

# Test whoami endpoint (should return 200 without auth)
check /v1/whoami 200

# Test me endpoint (should return 401 without auth)
check /v1/me 401

# Test Google login URL endpoint
check /v1/google/login_url 200

# Test Google callback endpoint (method not allowed without params)
check /v1/google/auth/callback 405

echo "🎉 All smoke tests passed!"
