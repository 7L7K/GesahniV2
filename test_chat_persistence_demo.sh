#!/bin/bash
# Demo script for chat persistence functionality
# This script demonstrates:
# 1. POST /v1/ask → returns rid and saves messages to DB
# 2. GET /v1/ask/replay/{rid} → retrieves persisted messages

echo "=== CHAT PERSISTENCE DEMO ==="
echo

# Configuration
API_BASE="http://localhost:8000"
TEST_USER_ID="test-user-123"
TEST_MESSAGE="Hello, this is a test message for persistence"

# Generate a test JWT token (simplified for demo)
# In real usage, you'd get this from your auth system
JWT_SECRET="test-secret-123456789012345678901234567890"
HEADER_TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdC11c2VyLTEyMyIsInNjb3BlcyI6WyJjYXJlOnJlc2lkZW50IiwibXVzaWM6Y29udHJvbCIsImNoYXQ6d3JpdGUiXSwic3ViIjoidGVzdC11c2VyLTEyMyIsInR5cGUiOiJhY2Nlc3MiLCJleHAiOjE3NTc3ODMyNDAsImlhdCI6MTc1Nzc4MTQ0MCwianRpIjoiNTY4MzY1NGNhNzA3NGE5MWI3ZWI2M2ViYzgzZTU1ZmYifQ.N2NhbNbk9CcgQy8X3YHa26JUgkfyHItQqcsXcfcdzt0"

echo "1. Testing POST /v1/ask (should save messages to DB)"
echo "   Request: $TEST_MESSAGE"
echo

RESPONSE=$(curl -s -X POST "$API_BASE/v1/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $HEADER_TOKEN" \
  -d "{\"prompt\": \"$TEST_MESSAGE\", \"model\": \"gpt-4o\"}")

echo "   Response:"
echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
echo

# Extract RID from response
RID=$(echo "$RESPONSE" | jq -r '.req_id // .rid' 2>/dev/null || echo "")

if [ -n "$RID" ] && [ "$RID" != "null" ]; then
    echo "2. Testing GET /v1/ask/replay/$RID (should retrieve persisted messages)"
    echo

    REPLAY_RESPONSE=$(curl -s -X GET "$API_BASE/v1/ask/replay/$RID" \
      -H "Authorization: Bearer $HEADER_TOKEN")

    echo "   Replay Response:"
    echo "$REPLAY_RESPONSE" | jq '.' 2>/dev/null || echo "$REPLAY_RESPONSE"
    echo

    # Verify the message was persisted
    MESSAGE_COUNT=$(echo "$REPLAY_RESPONSE" | jq -r '.message_count // 0' 2>/dev/null)
    if [ "$MESSAGE_COUNT" -gt 0 ]; then
        echo "✅ SUCCESS: $MESSAGE_COUNT messages persisted and retrieved!"
        echo "   Original message: '$TEST_MESSAGE'"
        RETRIEVED_CONTENT=$(echo "$REPLAY_RESPONSE" | jq -r '.messages[0].content // "N/A"' 2>/dev/null)
        echo "   Retrieved content: '$RETRIEVED_CONTENT'"
    else
        echo "❌ FAILED: No messages found in database"
    fi
else
    echo "❌ FAILED: Could not extract RID from ask response"
    echo "   Make sure the backend is running and the database is set up"
fi

echo
echo "=== DEMO COMPLETE ==="
echo
echo "Notes:"
echo "- Make sure the backend is running: uvicorn app.main:app --reload"
echo "- Make sure the database migration has been applied"
echo "- The JWT token used is for demo purposes only"

