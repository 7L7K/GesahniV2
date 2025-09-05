#!/usr/bin/env bash
set -euo pipefail

ORIGIN="http://localhost:3000"
API="http://localhost:8000"
COOKIES="$(mktemp)"
HDRS="$(mktemp)"

echo "== P0: Preflight should pass =="
curl -is -X OPTIONS "$API/v1/me" \
  -H "Origin: $ORIGIN" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,x-csrf-token,content-type" \
  | tee "$HDRS" | sed -n '1,20p'
grep -qi "Access-Control-Allow-Origin: $ORIGIN" "$HDRS" || { echo "❌ ACAO missing"; exit 1; }
grep -qi "Access-Control-Allow-Credentials: true" "$HDRS" || { echo "❌ ACAC missing"; exit 1; }

echo "== P1: /v1/me anon should be 401 (not CORS) =="
curl -is "$API/v1/me" -H "Origin: $ORIGIN" --cookie "$COOKIES" | sed -n '1,40p'

echo "== P2: CSRF token (if used) =="
curl -is "$API/csrf" -H "Origin: $ORIGIN" --cookie "$COOKIES" --cookie-jar "$COOKIES" | sed -n '1,40p'

echo "== P3: Login (adjust path/body to your API) =="
curl -is "$API/v1/login" \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: dummy" \
  --cookie "$COOKIES" --cookie-jar "$COOKIES" \
  --data '{"username":"test","password":"test"}' | sed -n '1,80p'

echo "== P4: /v1/me after login should be 200 =="
curl -is "$API/v1/me" -H "Origin: $ORIGIN" --cookie "$COOKIES" | sed -n '1,60p'

echo "== P5: Refresh path sanity (simulate expired access) =="
# Optionally delete access cookie to force refresh path
sed -i '' '/GSNH_AT/d' "$COOKIES" 2>/dev/null || true
curl -is -X POST "$API/v1/auth/refresh" -H "Origin: $ORIGIN" --cookie "$COOKIES" --cookie-jar "$COOKIES" | sed -n '1,60p'
curl -is "$API/v1/me" -H "Origin: $ORIGIN" --cookie "$COOKIES" | sed -n '1,60p'

echo "== DONE =="
