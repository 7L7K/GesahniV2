#!/usr/bin/env bash
set -euo pipefail

# Gesahni Development Stop Script
echo "🛑 Stopping Gesahni Development Environment"

# Patterns to look for (full command match via pgrep -f)
# More specific patterns to avoid killing unrelated processes
patterns=("uvicorn app.main:app" "next dev" "next-server" "pnpm dev" "npm run dev")

any=false
for pat in "${patterns[@]}"; do
  # Find matching PIDs (silent if none)
  pids=$(pgrep -f -- "$pat" || true)
  if [ -n "$pids" ]; then
    any=true
    echo "Found processes for '$pat': $pids"
    # Attempt graceful TERM first
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        kill -TERM "$pid" 2>/dev/null || true
      fi
    done

    # Give processes a moment to exit
    sleep 1

    # Force kill any remaining
    for pid in $pids; do
      if kill -0 "$pid" 2>/dev/null; then
        echo "Forcing kill PID $pid"
        kill -KILL "$pid" 2>/dev/null || true
      fi
    done
  fi
done

if [ "$any" = true ]; then
  echo "✅ Stopped matching development processes"
else
  echo "ℹ️  No matching development processes found"
fi

exit 0
