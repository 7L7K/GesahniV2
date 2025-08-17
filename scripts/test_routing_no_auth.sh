#!/usr/bin/env bash
set -euo pipefail
API="${API:-http://127.0.0.1:8000}"

# Set environment to bypass auth for testing
export REQUIRE_AUTH_FOR_ASK=0
export ASK_STRICT_BEARER=0

j(){ jq -r "$1" || true; }

run(){ name="$1"; body="$2";
  rid=$(uuidgen | tr '[:upper:]' '[:lower:]')
  curl -s "$API/v1/ask" -H 'Content-Type: application/json' \
    -H "X-RID:$rid" -d "$body" >/dev/null
  echo "$name $rid"
}

echo "🚀 Starting Router Drill Kit (No Auth)..."
echo ""

# Wait for server to be ready
echo "⏳ Waiting for server to be ready..."
until curl -s "$API/healthz/ready" >/dev/null 2>&1; do
  sleep 1
done
echo "✅ Server ready!"

echo ""
echo "🎯 Running routing tests..."

# Test 1: Light chat → LLaMA
run "light_chat_llama" '{"prompt":[{"role":"user","content":"hello world"}]}'

# Test 2: Heavy length → GPT
run "heavy_text_gpt"  '{"prompt":"'"$(python - <<'PY'
print('x '*350)
PY
)"'"}'

# Test 3: Explicit LLaMA override
run "override_llama"  '{"prompt":"yo","model":"llama3"}'

# Test 4: Explicit GPT override
run "override_gpt"    '{"prompt":"hey","model_override":"gpt-4o"}'

# Test 5: Unknown model → 400
echo "5. Unknown model test:"
curl -si "$API/v1/ask" -H 'Content-Type: application/json' \
  -d '{"prompt":"yo","model":"pingpong-9000"}' | head -n1

# Test 6: Dry-run (no vendor calls)
echo "6. Dry-run test:"
DEBUG_MODEL_ROUTING=1 curl -s "$API/v1/ask/dry-explain" \
  -H 'Content-Type: application/json' -d '{"prompt":"ping"}' | j '.picker_reason,.dry_run'

# Test 7: Nested input → normalized
run "nested_text"     '{"input":{"prompt":"nested"}}'

echo ""
echo "✅ Tests complete!"
