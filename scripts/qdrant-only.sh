#!/usr/bin/env bash
set -euo pipefail

echo "🗃️  Starting Gesahni Qdrant Vector Store Only"
echo "📋 Configuration:"
echo "  - Qdrant: http://localhost:6333"
echo "  - Data Directory: $(pwd)/_qdrant_data"
echo ""

# Ensure Qdrant is running (idempotent container management)
ensure_qdrant() {
  local NAME="gesahni-qdrant"
  local IMAGE="${QDRANT_IMAGE:-qdrant/qdrant:latest}"
  local PORT="${QDRANT_PORT:-6333}"
  local HOST_PORT="${QDRANT_HOST_PORT:-6333}"
  local DATA_DIR="${QDRANT_DATA_DIR:-$(pwd)/_qdrant_data}"

  mkdir -p "$DATA_DIR"

  # Exists?
  if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
    # Running?
    if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
      echo "✅ Qdrant '$NAME' already running."
    else
      echo "▶️  Starting existing Qdrant '$NAME'..."
      docker start "$NAME" >/dev/null
    fi
  else
    echo "🧰 Creating Qdrant '$NAME'…"
    docker run -d --name "$NAME" \
      -p "${HOST_PORT}:${PORT}" \
      -v "${DATA_DIR}:/qdrant/storage" \
      --health-cmd="curl -fsS http://localhost:${PORT}/readyz || exit 1" \
      --health-interval=5s --health-retries=10 --health-timeout=2s \
      "$IMAGE" >/dev/null
  fi

  # Wait for healthy
  echo -n "⏳ Waiting for Qdrant to be healthy"
  for i in {1..30}; do
    if docker inspect --format='{{json .State.Health.Status}}' "$NAME" 2>/dev/null | grep -q healthy; then
      echo; echo "✅ Qdrant healthy."
      return 0
    fi
    echo -n "."
    sleep 1
  done

  echo; echo "❌ Qdrant failed to become healthy. Showing last 50 logs:"
  docker logs --tail=50 "$NAME"
  exit 1
}

# Start Qdrant if Docker is available
if command -v docker >/dev/null 2>&1; then
    ensure_qdrant

    echo ""
    echo "✅ Qdrant ready!"
    echo "🗃️  Qdrant: http://localhost:6333"
    echo "📊 Dashboard: http://localhost:6333/dashboard"
    echo "📁 Data Directory: $(pwd)/_qdrant_data"
    echo ""
    echo "💡 Use this for vector store testing without application code"
    echo "🛑 Press Ctrl+C to stop Qdrant"

    # Wait for interrupt
    trap 'echo ""; echo "🛑 Stopping Qdrant..."; docker stop gesahni-qdrant >/dev/null 2>&1 || true; exit 0' INT
    wait
else
    echo "❌ Docker not available - cannot start Qdrant"
    exit 1
fi
