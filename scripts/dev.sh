#!/usr/bin/env bash
set -euo pipefail

echo "🚀 Starting Gesahni Development Environment"
echo "📋 Configuration:"
echo "  - Frontend: http://localhost:3000 (IPv4-first DNS)"
echo "  - Backend: http://127.0.0.1:8000 (IPv4 only)"
echo "  - API Origin: http://127.0.0.1:8000"
echo ""

# Kill any existing processes
echo "🧹 Cleaning up existing processes..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
sleep 2

# Start backend
echo "🔧 Starting backend (IPv4 only)..."
cd "$(dirname "$0")/.."
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
until curl -s http://127.0.0.1:8000/healthz/ready >/dev/null 2>&1; do
  sleep 1
done
echo "✅ Backend ready at http://127.0.0.1:8000"

# Start frontend
echo "🎨 Starting frontend (IPv4-first DNS)..."
cd frontend
NODE_OPTIONS="--dns-result-order=ipv4first --max-old-space-size=4096" NEXT_PUBLIC_SITE_URL=http://localhost:3000 CLERK_SIGN_IN_URL=http://localhost:3000/sign-in CLERK_SIGN_UP_URL=http://localhost:3000/sign-up CLERK_AFTER_SIGN_IN_URL=http://localhost:3000 CLERK_AFTER_SIGN_UP_URL=http://localhost:3000 pnpm dev &
FRONTEND_PID=$!

# Wait for frontend to be ready
echo "⏳ Waiting for frontend to be ready..."
until curl -s http://localhost:3000 >/dev/null 2>&1; do
  sleep 1
done
echo "✅ Frontend ready at http://localhost:3000"

echo ""
echo "🎉 Development environment started!"
echo "📊 Backend: http://127.0.0.1:8000"
echo "🎨 Frontend: http://localhost:3000"
echo "📈 Metrics: http://127.0.0.1:8000/metrics"
echo "🏥 Health: http://127.0.0.1:8000/healthz/ready"
echo ""
echo "💡 Remember to clear localhost cookies in your browser!"
echo "🛑 Press Ctrl+C to stop both services"

# Wait for interrupt
trap 'echo ""; echo "🛑 Stopping services..."; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true; exit 0' INT
wait
