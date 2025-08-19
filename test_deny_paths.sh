#!/bin/bash

# Test script to demonstrate deny path logging
# This script shows how to test the various deny paths we've added logging to

echo "Testing Deny Path Logging"
echo "========================="
echo

# Test 1: CSRF missing header (when CSRF is enabled)
echo "1. Testing CSRF missing header..."
echo "   Expected log: deny: csrf_missing_header header=<None> cookie=<None>"
echo "   Run this when CSRF_ENABLED=1:"
echo "   curl -X POST http://localhost:8000/v1/profile -H 'Content-Type: application/json' -d '{\"test\": \"data\"}'"
echo

# Test 2: Missing token
echo "2. Testing missing token..."
echo "   Expected log: deny: missing_token"
echo "   Run this when JWT_SECRET is set:"
echo "   curl -X POST http://localhost:8000/v1/ask -H 'Content-Type: application/json' -d '{\"question\": \"test\"}'"
echo

# Test 3: Missing scope
echo "3. Testing missing scope..."
echo "   Expected log: deny: missing_scope scope=<admin:write> available=<admin:read>"
echo "   Run this with a token that has 'admin:read' but needs 'admin:write':"
echo "   curl -X POST http://localhost:8000/v1/admin/config -H 'Authorization: Bearer <token_with_admin_read>'"
echo

# Test 4: Rate limiting
echo "4. Testing rate limiting..."
echo "   Expected log: deny: rate_limit_exceeded key=<...> limit=<...> window=<...> retry_after=<...>"
echo "   Run this repeatedly to hit rate limits:"
echo "   for i in {1..100}; do curl -X POST http://localhost:8000/v1/ask -H 'Content-Type: application/json' -d '{\"question\": \"test\"}'; done"
echo

# Test 5: WebSocket origin validation
echo "5. Testing WebSocket origin validation..."
echo "   Expected log: deny: origin_not_allowed origin=<...>"
echo "   Run this with a different origin:"
echo "   curl -H 'Origin: http://evil.com' http://localhost:8000/v1/ws/music"
echo

echo "To see the logs, check your server logs or run with increased verbosity:"
echo "LOG_LEVEL=DEBUG python -m uvicorn app.main:app --reload"
echo
echo "The deny path logs will help you quickly identify why requests are being rejected."
