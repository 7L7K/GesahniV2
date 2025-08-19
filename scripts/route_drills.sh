#!/usr/bin/env bash
set -euo pipefail
API="${API:-http://localhost:8000}"

j(){ jq -r "$1" || true; }

run(){ name="$1"; body="$2";
  rid=$(uuidgen | tr '[:upper:]' '[:lower:]')
  curl -s "$API/v1/ask" -H 'Content-Type: application/json' \
    -H "X-RID:$rid" -d "$body" >/dev/null
  echo "$name $rid"
}

echo "🚀 Starting Router Drill Kit..."
echo "Make sure server is running: uvicorn app.main:app --port 8000 --log-level info --no-access-log"
echo ""

# Wait for server to be ready
echo "⏳ Waiting for server to be ready..."
until curl -s "$API/healthz/ready" >/dev/null 2>&1; do
  sleep 1
done
echo "✅ Server ready!"

echo ""
echo "🎯 Running 12-case routing drill..."

# 1 Light chat → LLaMA
run "light_chat_llama" '{"prompt":[{"role":"user","content":"hello world"}]}'

# 2 Heavy length → GPT
run "heavy_text_gpt"  '{"prompt":"'"$(python - <<'PY'
print('x '*350)
PY
)"'"}'

# 3 Heavy tokens (messages) → GPT
run "heavy_msgs_gpt"  '{"messages":[{"role":"user","content":"'"$(python - <<'PY'
print('word '*1200)
PY
)"'"}]}'

# 4 Explicit LLaMA override
run "override_llama"  '{"prompt":"yo","model":"llama3"}'

# 5 Explicit GPT override
run "override_gpt"    '{"prompt":"hey","model_override":"gpt-4o"}'

# 6 Unknown model → 400
echo "6. Unknown model test:"
curl -si "$API/v1/ask" -H 'Content-Type: application/json' \
  -d '{"prompt":"yo","model":"pingpong-9000"}' | head -n1

# 7 Streaming LLaMA
echo "7. Streaming LLaMA test:"
curl -N "$API/v1/ask/stream" -H 'Content-Type: application/json' \
  -d '{"prompt":"stream please","model":"llama3","stream":true}' | head -n3 || true

# 8 Streaming GPT
echo "8. Streaming GPT test:"
curl -N "$API/v1/ask/stream" -H 'Content-Type: application/json' \
  -d '{"prompt":"stream please","model_override":"gpt-4o","stream":true}' | head -n3 || true

# 9 LLaMA breaker → GPT
echo "9. LLaMA circuit breaker test:"
LLAMA_CIRCUIT_OPEN=true curl -s "$API/v1/ask" -H 'Content-Type: application/json' \
  -d '{"prompt":"hello"}' >/dev/null || true

# 10 GPT breaker → LLaMA
echo "10. GPT circuit breaker test:"
GPT_CIRCUIT_OPEN=true curl -s "$API/v1/ask" -H 'Content-Type: application/json' \
  -d '{"prompt":"hello"}' >/dev/null || true

# 11 Dry-run (no vendor calls)
echo "11. Dry-run test:"
DEBUG_MODEL_ROUTING=1 curl -s "$API/v1/ask/dry-explain" \
  -H 'Content-Type: application/json' -d '{"prompt":"ping"}' | j '.picker_reason,.dry_run'

# 12 Nested input → normalized
run "nested_text"     '{"input":{"prompt":"nested"}}'

echo ""
echo "✅ 12-case drill complete!"
echo "📊 Check logs for golden traces and run verify_receipts.sh to validate"
