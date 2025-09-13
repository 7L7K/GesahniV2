#!/usr/bin/env bash
set -euo pipefail

# Disable rate limiting for testing
export RATE_LIMIT_MODE=off

JAR=/tmp/gs.cookies
rm -f "$JAR"

echo ">>> Same-origin via Next proxy (http://localhost:3000)"
curl -s -i -c "$JAR" -X POST "http://localhost:3000/v1/auth/login?username=demo" | \
  awk '/^Set-Cookie:/ {print}'
echo "— whoami:"
curl -s -b "$JAR" "http://localhost:3000/v1/whoami" | jq .

echo ">>> Cross-origin direct to backend (http://localhost:8000)"
echo "— Note: localhost:3000 and localhost:8000 share domain 'localhost', so cookies are shared"
rm -f "$JAR"
curl -s -i -c "$JAR" -X POST "http://localhost:8000/v1/auth/login?username=demo" | \
  awk '/^Set-Cookie:/ {print}'
echo "— whoami (against backend) with saved jar:"
curl -s -b "$JAR" "http://localhost:8000/v1/whoami" | jq .

echo ""
echo ">>> Cross-origin test with different domain (127.0.0.1:8000) — this should fail"
echo "— Testing if 127.0.0.1:8000 cookies are isolated from localhost:3000"
rm -f "$JAR"
curl -s -i -c "$JAR" -X POST "http://127.0.0.1:8000/v1/auth/login?username=demo" | \
  awk '/^Set-Cookie:/ {print}'
echo "— whoami (against 127.0.0.1:8000) with saved jar:"
curl -s -b "$JAR" "http://127.0.0.1:8000/v1/whoami" | jq .

echo ""
echo ">>> Browser simulation: Testing if localhost:3000 cookies work on 127.0.0.1:8000"
echo "— This simulates a browser trying to use localhost cookies on 127.0.0.1"
curl -s -b "$JAR" "http://127.0.0.1:8000/v1/whoami" | jq .
