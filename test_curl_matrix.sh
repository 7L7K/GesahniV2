#!/bin/bash
# Router Drill Kit - 12-case curl matrix for testing routing decisions

echo "🚀 Starting Router Drill Kit..."
echo "Make sure server is running: uvicorn app.main:app --port 8000 --log-level info --no-access-log"
echo ""

# Wait for server to be ready
echo "⏳ Waiting for server to be ready..."
until curl -s localhost:8000/healthz/ready >/dev/null 2>&1; do
    sleep 1
done
echo "✅ Server ready!"

echo ""
echo "🎯 Running 12-case curl matrix..."
echo "=================================="

# 1) Light chat -> LLaMA
echo "1. Light chat -> LLaMA"
curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":[{"role":"user","content":"hello world"}]}' >/dev/null
echo "✅ Done"

# 2) Heavy length -> GPT
echo "2. Heavy length -> GPT"
curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":"Write a detailed Python script to scrape multiple sites with retries, backoff, and tests. Include comprehensive error handling, logging, rate limiting, and unit tests. The script should handle various HTTP status codes, implement exponential backoff for failed requests, and provide detailed progress reporting. Make sure to include proper documentation and type hints throughout the codebase."}' >/dev/null
echo "✅ Done"

# 3) Heavy tokens (messages) -> GPT
echo "3. Heavy tokens (messages) -> GPT"
curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$(python -c 'print("x "*2000)')\"}]}" >/dev/null
echo "✅ Done"

# 4) Explicit LLaMA override
echo "4. Explicit LLaMA override"
curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":"yo","model":"llama3"}' >/dev/null
echo "✅ Done"

# 5) Explicit GPT override
echo "5. Explicit GPT override"
curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":"hey","model_override":"gpt-4o"}' >/dev/null
echo "✅ Done"

# 6) Unknown model -> 400
echo "6. Unknown model -> 400"
curl -i localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":"yo","model":"pingpong-9000"}' 2>/dev/null | head -n 5
echo "✅ Done"

# 7) Streaming flag honored (LLaMA)
echo "7. Streaming flag honored (LLaMA)"
curl -N localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":"stream please","model":"llama3","stream":true}' >/dev/null &
sleep 2
kill %1 2>/dev/null
echo "✅ Done"

# 8) Streaming flag honored (GPT)
echo "8. Streaming flag honored (GPT)"
curl -N localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":"stream please","model_override":"gpt-4o","stream":true}' >/dev/null &
sleep 2
kill %1 2>/dev/null
echo "✅ Done"

# 9) LLaMA breaker (forces GPT)
echo "9. LLaMA breaker (forces GPT)"
LLAMA_CIRCUIT_OPEN=true curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":"hello"}' >/dev/null
echo "✅ Done"

# 10) GPT breaker (forces LLaMA) - Note: This would need GPT circuit breaker implementation
echo "10. GPT breaker (forces LLaMA) - Skipped (not implemented)"
# GPT_CIRCUIT_OPEN=true curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
#   -d '{"prompt":"hello"}' >/dev/null
echo "⏭️  Skipped"

# 11) Dry-run on (no model calls)
echo "11. Dry-run on (no model calls)"
DEBUG_MODEL_ROUTING=1 curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"prompt":"ping"}' >/dev/null
echo "✅ Done"

# 12) Nested input -> normalized to text
echo "12. Nested input -> normalized to text"
curl -s localhost:8000/v1/ask -H 'Content-Type: application/json' \
  -d '{"input":{"prompt":"nested"}}' >/dev/null
echo "✅ Done"

echo ""
echo "🎯 Matrix complete! Check server logs for GOLDEN_TRACE entries."
echo ""
echo "📊 To extract routing decisions, run:"
echo "grep 'GOLDEN_TRACE' | jq -r '.rid, .shape, .normalized_from, .override_in, .intent, .picker_reason, .chosen_vendor + \"/\" + .chosen_model, .dry_run, .cb_user_open, .cb_global_open'"
echo ""
echo "🔍 To test shadow routing:"
echo "curl -s localhost:8000/v1/ask/dry-explain -H 'Content-Type: application/json' -d '{\"prompt\":\"hello\"}' | jq"
