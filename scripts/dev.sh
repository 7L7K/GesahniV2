#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting Gesahni Development Environment"
echo "📋 Configuration:"
echo "  - Frontend: http://localhost:3000 (bound to 127.0.0.1)"
echo "  - Backend: http://localhost:8000 (bound to 127.0.0.1)"
echo "  - API Origin: http://localhost:8000"
echo ""

# Environment variables loaded by direnv (.envrc)
echo "📝 Environment loaded via direnv (.env file)"

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
      --health-cmd="apt-get update && apt-get install -y curl && curl -fsS http://0.0.0.0:${PORT}/readyz || exit 1" \
      --health-interval=10s --health-retries=10 --health-timeout=30s \
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

# Ensure Redis is running
ensure_redis() {
  # Check if Redis is already running
  if pgrep -f redis-server >/dev/null; then
    echo "✅ Redis already running."
    return 0
  fi

  # Try to start Redis via Homebrew
  if command -v redis-server >/dev/null 2>&1; then
    echo "▶️  Starting Redis via Homebrew..."
    redis-server --daemonize yes
    sleep 2
    if pgrep -f redis-server >/dev/null; then
      echo "✅ Redis started via Homebrew."
      return 0
    fi
  fi

  # Fallback to Docker
  if command -v docker >/dev/null 2>&1; then
    local NAME="gesahni-redis"
    local IMAGE="redis:7-alpine"

    # Check if container exists
    if docker ps -a --format '{{.Names}}' | grep -qx "$NAME"; then
      if docker ps --format '{{.Names}}' | grep -qx "$NAME"; then
        echo "✅ Redis container '$NAME' already running."
      else
        echo "▶️  Starting existing Redis container '$NAME'..."
        docker start "$NAME" >/dev/null
      fi
    else
      echo "🧰 Creating Redis container '$NAME'..."
      docker run -d --name "$NAME" \
        -p "6379:6379" \
        --health-cmd="redis-cli ping" \
        --health-interval=5s --health-retries=5 --health-timeout=3s \
        "$IMAGE" --appendonly yes >/dev/null
    fi

    # Wait for healthy
    echo -n "⏳ Waiting for Redis to be healthy..."
    for i in {1..30}; do
      if docker inspect --format='{{json .State.Health.Status}}' "$NAME" 2>/dev/null | grep -q healthy; then
        echo; echo "✅ Redis healthy."
        return 0
      fi
      echo -n "."
      sleep 1
    done
    echo; echo "❌ Redis container failed to become healthy."
    return 1
  fi

  echo "❌ No Redis installation found. Please install Redis via:"
  echo "   brew install redis"
  echo "   or start it manually: redis-server --daemonize yes"
  return 1
}

# Start Redis (optional but recommended for stable sessions)
if command -v redis-server >/dev/null 2>&1 || command -v docker >/dev/null 2>&1; then
    if ensure_redis; then
        echo "✅ Redis available"
    else
        echo "⚠️  Redis startup failed - using in-memory session store"
    fi
else
    echo "ℹ️  Redis not available - using in-memory session store"
fi

# Start Qdrant if Docker is available
if command -v docker >/dev/null 2>&1; then
    if ensure_qdrant; then
        echo "✅ Qdrant available"
    else
        echo "⚠️  Qdrant startup failed - using fallback vector store"
    fi
else
    echo "ℹ️  Docker not available - using fallback vector store"
fi

# Setup frontend environment
echo "🎨 Setting up frontend environment..."
if [ -f "frontend/env.localhost" ]; then
    cp frontend/env.localhost frontend/.env.local 2>/dev/null || true
    echo "✅ Frontend environment configured"
else
    echo "⚠️  Warning: frontend/env.localhost not found"
fi

# Kill any existing processes (aggressive cleanup)
echo "🧹 Cleaning up existing processes..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true
pkill -f "npm" 2>/dev/null || true

# Kill processes by port (including stale connections)
for port in 8000 3000; do
  pids=$(lsof -t -iTCP:$port 2>/dev/null || true)
  if [ -n "$pids" ]; then
    echo "Killing processes on port $port: $pids"
    for pid in $pids; do
      kill -TERM "$pid" 2>/dev/null || true
    done
  fi
done

sleep 3

# Force kill any remaining processes
for port in 8000 3000; do
  remaining_pids=$(lsof -t -iTCP:$port 2>/dev/null || true)
  if [ -n "$remaining_pids" ]; then
    echo "Force-killing remaining processes on port $port: $remaining_pids"
    for pid in $remaining_pids; do
      kill -KILL "$pid" 2>/dev/null || true
    done
  fi
done

# Start backend
echo "🔧 Starting backend (bound to 127.0.0.1)..."
cd "$(dirname "$0")/.."
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# Health probe with timeout - fail fast instead of zombie waiting
echo "⏳ Waiting for backend to be ready..."
for i in {1..20}; do
  # Check if process is still running
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    echo "❌ Backend process died. Check logs above."
    exit 1
  fi
  # Check health endpoint
  if curl -sf http://127.0.0.1:8000/healthz/ready >/dev/null; then
    echo "✅ Backend ready"
    break
  fi
  sleep 0.5
done

# Final health check - fail if not ready
if ! curl -sf http://127.0.0.1:8000/healthz/ready >/dev/null; then
  echo "❌ Backend not ready in time"
  exit 1
fi

# Start frontend
echo "🎨 Starting frontend (bound to 127.0.0.1)..."
cd frontend
# Set PORT to 3000 to ensure Next.js uses the correct port
export PORT=3000
NODE_OPTIONS="--dns-result-order=ipv4first --max-old-space-size=4096" npm run dev &
FRONTEND_PID=$!

# Wait for frontend to be ready
echo "⏳ Waiting for frontend to be ready..."
until curl -s http://localhost:3000 >/dev/null 2>&1; do
  sleep 1
done
echo "✅ Frontend ready at http://localhost:3000"

echo ""
echo "🎉 Development environment started!"
echo "📊 Backend: http://localhost:8000"
echo "🎨 Frontend: http://localhost:3000"
echo "📈 Metrics: http://localhost:8000/metrics"
echo "🏥 Health: http://localhost:8000/healthz/ready"
echo ""
echo "💡 Remember to clear localhost cookies in your browser!"
echo "🛑 Press Ctrl+C to stop both services"

# Wait for interrupt
trap 'echo ""; echo "🛑 Stopping services..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true; exit 0' INT
wait
