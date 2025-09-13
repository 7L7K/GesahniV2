#!/bin/bash
# Demo script for testing capped exponential backoff functionality

echo "=== CHAT BACKOFF DEMO ==="
echo

echo "1. Testing backoff configuration:"
echo "   - Initial delay: 400ms"
echo "   - Max delay: 5 seconds"
echo "   - Max attempts: 4"
echo "   - Multiplier: 2x"
echo

echo "2. Manual verification steps:"
echo "   a) Start the backend: uvicorn app.main:app --reload"
echo "   b) Start the frontend: cd frontend && npm run dev"
echo "   c) Open browser to http://localhost:3000/chat"
echo "   d) Send a message - should work normally"
echo

echo "3. Simulate network failures:"
echo "   a) Kill the backend server (Ctrl+C)"
echo "   b) Try sending a message in the chat"
echo "   c) Expected behavior:"
echo "      - First attempt fails immediately"
echo "      - Retry 1/4 after 400ms delay"
echo "      - Retry 2/4 after 800ms delay"
echo "      - Retry 3/4 after 1600ms delay"
echo "      - Retry 4/4 after 3200ms delay (capped at 5s)"
echo "      - Final failure after 4 attempts"
echo

echo "4. Restore backend and verify success:"
echo "   a) Restart backend: uvicorn app.main:app --reload"
echo "   b) Send another message"
echo "   c) Should work immediately without retries"
echo

echo "5. Test non-retryable errors:"
echo "   a) Try sending with invalid auth (logout first)"
echo "   b) Should get 401 and NOT retry"
echo

echo "=== MONITORING LOGS ==="
echo "Watch the browser console for messages like:"
echo "   [chat.sendPrompt] Retry 1/4 after 400ms delay"
echo "   [chat.sendPrompt] Retry 2/4 after 800ms delay"
echo "   [chat.sendPrompt] Backoff aborted - auth/validation error (status 401)"
echo "   [chat.sendPrompt] Backoff failed after 4 attempts"
echo

echo "=== EXPECTED DELAY SEQUENCE ==="
echo "Attempt 1: immediate"
echo "Attempt 2: +400ms  (400ms total)"
echo "Attempt 3: +800ms  (1200ms total)"
echo "Attempt 4: +1600ms (2800ms total)"
echo "Attempt 5: +3200ms (6000ms total, but capped at 5000ms)"
echo

echo "Demo complete! Follow the steps above to test the backoff functionality."
