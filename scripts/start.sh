#!/usr/bin/env bash
set -euo pipefail

# Gesahni Development Start Script
# Simple one-command startup for both backend and frontend

echo "🚀 Starting Gesahni Development Environment"
echo "=========================================="

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping development environment..."
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "pnpm dev" 2>/dev/null || true
    exit 0
}

# Set up trap for cleanup
trap cleanup INT TERM

# Load environment if available
if [ -f "env.localhost" ]; then
    echo "📝 Loading localhost configuration..."
    export $(grep -v '^#' env.localhost | xargs)
fi

# Setup frontend environment
if [ -f "frontend/env.localhost" ]; then
    cp frontend/env.localhost frontend/.env.local 2>/dev/null || true
fi

# Kill any existing processes
echo "🧹 Cleaning up existing processes..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "pnpm dev" 2>/dev/null || true
sleep 2

# Start backend
echo "🔧 Starting backend (IPv6)..."
source .venv/bin/activate
uvicorn app.main:app --host :: --port 8000 --reload &
BACKEND_PID=$!

# Wait for backend
echo "⏳ Waiting for backend..."
until curl -s http://localhost:8000/healthz/ready >/dev/null 2>&1; do
    sleep 1
done
echo "✅ Backend ready at http://localhost:8000"

# Start frontend
echo "🎨 Starting frontend (IPv6)..."
cd frontend
export PORT=3000  # Ensure correct port
npm run dev &
FRONTEND_PID=$!
cd ..

# Wait for frontend
echo "⏳ Waiting for frontend..."
until curl -s http://localhost:3000 >/dev/null 2>&1; do
    sleep 1
done
echo "✅ Frontend ready at http://localhost:3000"

echo ""
echo "🎉 Development environment started!"
echo "📊 Backend:  http://localhost:8000"
echo "🎨 Frontend: http://localhost:3000"
echo "🏥 Health:   http://localhost:8000/healthz/ready"
echo ""
echo "💡 Commands:"
echo "   - 'gesahni-stop' to stop both services"
echo "   - 'gesahni-restart' to restart both services"
echo "   - 'gesahni-clear' to clear cookies and restart"
echo ""
echo "🛑 Press Ctrl+C to stop both services"

# Wait for interrupt
wait
