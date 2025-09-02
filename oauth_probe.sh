#!/usr/bin/env bash
set -euo pipefail

# ==== CONFIG: tweak if needed =====
BACKEND="${BACKEND:-http://127.0.0.1:8000}"
FRONTEND="${FRONTEND:-http://127.0.0.1:3000}"   # use SAME HOSTNAME as backend in dev (see notes)
LOGIN_EP="${LOGIN_EP:-/v1/auth/google/login_url}"
CB_EP="${CB_EP:-/v1/auth/google/callback}"
STATUS_EP="${STATUS_EP:-/v1/integrations/google/status}"

JAR="${JAR:-/tmp/google_oauth.jar}"
LOGIN_JSON="/tmp/google_login.json"
CB_HEADERS="/tmp/google_cb_headers.txt"

echo "💿 Reset cookie jar: $JAR"
rm -f "$JAR" "$LOGIN_JSON" "$CB_HEADERS"

echo "�� 1) Get login URL (capture cookies)"
curl -sS -c "$JAR" "$BACKEND$LOGIN_EP?next=$FRONTEND/settings#google=connected" | tee "$LOGIN_JSON" >/dev/null

AUTH_URL=$(jq -r '.auth_url // .url // ""' "$LOGIN_JSON" 2>/dev/null || true)
if [[ -z "$AUTH_URL" || "$AUTH_URL" == "null" ]]; then
  echo "❌ Could not find auth_url in $LOGIN_JSON"
  echo "   Contents:"
  cat "$LOGIN_JSON"
  exit 1
fi
echo "   auth_url = $AUTH_URL"

echo "🧩 2) Extract state"
STATE=$(python3 - <<'PY'
import os
from urllib.parse import urlparse, parse_qs
u = os.environ.get('AUTH_URL','')
q = parse_qs(urlparse(u).query)
print(q.get('state', [''])[0])
PY
)
if [[ -z "$STATE" ]]; then
  echo "❌ No state param found in auth_url"
  exit 1
fi
echo "   state = $STATE"

echo "↩️ 3) Simulate callback (invalid code) to inspect headers & cookies"
curl -sS -i -b "$JAR" -c "$JAR" "$BACKEND$CB_EP?code=THIS_IS_BAD&state=$STATE" -o /dev/null -D "$CB_HEADERS" || true

echo "--- Set-Cookie lines from callback response ---"
awk 'BEGIN{IGNORECASE=1} /^set-cookie:/ {print}' "$CB_HEADERS" | sed 's/\r$//'

echo "\n--- Cookie jar host binding (cookie jar contents) ---"
# show host and cookie names
awk '!/^#/ {print}' "$JAR" | awk '{print $1" "$6}' | column -t | sed -n '1,20p'

echo "\n--- /status JSON (using cookie jar) ---"
curl -sS -b "$JAR" "$BACKEND$STATUS_EP" | jq -C .

echo "\n✅ probe complete."
