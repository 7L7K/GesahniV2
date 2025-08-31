#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting Gesahni Development Environment"
echo "📋 Configuration:"
echo "  - Frontend: http://localhost:3000 (bound to 127.0.0.1)"
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

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
timeout=30  # Increased timeout for slower machines
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
echo "✅ Backend ready at http://localhost:8000"

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
