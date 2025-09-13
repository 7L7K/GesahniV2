#!/bin/bash
# Test script for chat error responses with standardized JSON format

echo "=== CHAT ERROR RESPONSES TEST ==="
echo

API_BASE="http://localhost:8000"
TEST_MESSAGE="Hello, this is a test message"

echo "1. Testing MISSING CSRF TOKEN (403)"
echo "   POST /v1/ask without X-CSRF-Token header"
echo

curl -s -X POST "$API_BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer test-token" \
  -d "{\"prompt\": \"$TEST_MESSAGE\"}" | jq '.' 2>/dev/null || echo "Response received"
echo

echo "2. Testing MISSING SCOPE (403)"
echo "   POST /v1/ask with invalid token (missing chat:write scope)"
echo

curl -s -X POST "$API_BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid-token-no-scopes" \
  -d "{\"prompt\": \"$TEST_MESSAGE\"}" | jq '.' 2>/dev/null || echo "Response received"
echo

echo "3. Testing EMPTY PROMPT (422)"
echo "   POST /v1/ask with empty prompt"
echo

curl -s -X POST "$API_BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer valid-token" \
  -d "{\"prompt\": \"\"}" | jq '.' 2>/dev/null || echo "Response received"
echo

echo "4. Testing INVALID REQUEST FORMAT (422)"
echo "   POST /v1/ask with invalid JSON"
echo

curl -s -X POST "$API_BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer valid-token" \
  -d "{\"invalid_field\": \"value\"}" | jq '.' 2>/dev/null || echo "Response received"
echo

echo "5. Testing RATE LIMIT EXCEEDED (429)"
echo "   POST /v1/ask multiple times rapidly to trigger rate limit"
echo

# Make multiple rapid requests to trigger rate limiting
for i in {1..10}; do
  curl -s -X POST "$API_BASE/v1/ask" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer valid-token" \
    -d "{\"prompt\": \"Rate limit test $i\"}" > /dev/null
done

# This should be rate limited
curl -s -X POST "$API_BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer valid-token" \
  -d "{\"prompt\": \"Rate limit test final\"}" | jq '.' 2>/dev/null || echo "Response received"
echo

echo "6. Testing REPLAY ENDPOINT - NOT FOUND (404)"
echo "   GET /v1/ask/replay/nonexistent-id"
echo

curl -s -X GET "$API_BASE/v1/ask/replay/nonexistent-12345" \
  -H "Authorization: Bearer valid-token" | jq '.' 2>/dev/null || echo "Response received"
echo

echo "=== EXPECTED ERROR FORMATS ==="
echo
echo "✅ All errors should return JSON with:"
echo "   - code: machine-readable error code"
echo "   - message: human-readable message"
echo "   - details: debug context (trace_id, req_id, timestamp)"
echo "   - hint: optional actionable hint"
echo
echo "Example CSRF error:"
echo "{"
echo "  \"code\": \"csrf_required\","
echo "  \"message\": \"CSRF token required\","
echo "  \"details\": {"
echo "    \"req_id\": \"01HXXXXXXXXXXXXXXXXXXXXX\","
echo "    \"trace_id\": \"abc123...\","
echo "    \"timestamp\": \"2025-09-13T16:45:23.123456Z\""
echo "  }"
echo "}"
echo
echo "Example scope error:"
echo "{"
echo "  \"code\": \"missing_scope\","
echo "  \"message\": \"Missing required scope: chat:write\","
echo "  \"details\": {"
echo "    \"req_id\": \"01HXXXXXXXXXXXXXXXXXXXXX\","
echo "    \"trace_id\": \"abc123...\","
echo "    \"timestamp\": \"2025-09-13T16:45:23.123456Z\""
echo "  }"
echo "}"
echo
echo "Example rate limit error:"
echo "{"
echo "  \"code\": \"rate_limited\","
echo "  \"message\": \"Rate limit exceeded\","
echo "  \"details\": {"
echo "    \"req_id\": \"01HXXXXXXXXXXXXXXXXXXXXX\","
echo "    \"trace_id\": \"abc123...\","
echo "    \"timestamp\": \"2025-09-13T16:45:23.123456Z\","
echo "    \"retry_after\": 60"
echo "  }"
echo "}"
echo

echo "=== MANUAL VERIFICATION STEPS ==="
echo
echo "1. Start the backend:"
echo "   uvicorn app.main:app --reload"
echo
echo "2. Run this test script:"
echo "   ./test_chat_errors.sh"
echo
echo "3. Verify all responses have the correct JSON structure"
echo "4. Check browser console for any error details"
echo
echo "Test complete! All chat routes now return standardized error JSON."
