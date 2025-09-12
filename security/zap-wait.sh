#!/usr/bin/env bash
set -euo pipefail
echo "[zap-wait] waiting for targets…"

wait_for() {
  local url="$1" name="$2" tries=60
  for i in $(seq 1 $tries); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[zap-wait] $name is up: $url"
      return 0
    fi
    sleep 2
  done
  echo "[zap-wait] TIMEOUT: $name didn't start ($url)" >&2
  exit 1
}

# Adjust these to your actual health endpoints:
wait_for "http://localhost:3000" "frontend"
wait_for "http://localhost:8000/healthz/ready" "backend"
