#!/usr/bin/env bash
set -euo pipefail

echo "🔧 Starting Gesahni Backend Only"
echo "📋 Configuration:"
echo "  - Backend: http://localhost:8000 (bound to 127.0.0.1)"
echo "  - API Origin: http://localhost:8000"
echo ""

# Load centralized localhost configuration
if [ -f "env.localhost" ]; then
    echo "📝 Loading centralized localhost configuration..."
    export $(grep -v '^#' env.localhost | xargs)
else
    echo "⚠️  Warning: env.localhost not found, using default configuration"
fi

# Ensure Qdrant is running (backend needs vector store)
if command -v docker >/dev/null 2>&1; then
    echo "🗃️  Ensuring Qdrant is running..."
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
    ensure_qdrant
else
    echo "⚠️  Docker not available, assuming Qdrant is running externally"
fi

# Kill any existing backend processes
echo "🧹 Cleaning up existing backend processes..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 2

# Force kill any remaining backend processes on port 8000
pids=$(lsof -t -iTCP:8000 2>/dev/null || true)
if [ -n "$pids" ]; then
    echo "Force-killing processes on port 8000: $pids"
    for pid in $pids; do
        kill -KILL "$pid" 2>/dev/null || true
    done
fi

# Start backend
echo "🔧 Starting backend (bound to 127.0.0.1)..."
cd "$(dirname "$0")/.."
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
timeout=30
counter=0
while ! curl -s http://localhost:8000/healthz/ready >/dev/null 2>&1; do
  if [ $counter -ge $timeout ]; then
    echo "⚠️  Backend taking longer than expected, but continuing..."
    break
  fi
  sleep 1
  counter=$((counter + 1))
  echo "   … still waiting ($counter/$timeout)"
done

echo ""
echo "✅ Backend ready!"
echo "📊 Backend: http://localhost:8000"
echo "📈 Metrics: http://localhost:8000/metrics"
echo "🏥 Health: http://localhost:8000/healthz/ready"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "🛑 Press Ctrl+C to stop backend"

# Wait for interrupt
trap 'echo ""; echo "🛑 Stopping backend..."; kill $BACKEND_PID 2>/dev/null || true; exit 0' INT
wait
