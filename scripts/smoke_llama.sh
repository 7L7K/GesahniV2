#!/bin/bash
# Simple health check for Ollama's LLaMA endpoint.
# Uses POST /api/generate instead of /api/ping.
# Exit codes: 0 = healthy, 1 = unhealthy.

HOST="${OLLAMA_URL:-http://localhost:11434}"
MODEL="${OLLAMA_MODEL:-llama3}"
# Override defaults via OLLAMA_URL/OLLAMA_MODEL or -H/-M flags.

while getopts "H:M:" opt; do
  case "$opt" in
    H) HOST="$OPTARG" ;;
    M) MODEL="$OPTARG" ;;
  esac
done

# Make request; capture HTTP status code.
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$HOST/api/generate" \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"hi\"}") || STATUS=000

if [ "$STATUS" -eq 200 ]; then
  exit 0
else
  exit 1
fi
