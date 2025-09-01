#!/usr/bin/env bash
set -euo pipefail

echo "🎨 Starting Gesahni Frontend Only"
echo "📋 Configuration:"
echo "  - Frontend: http://localhost:3000 (bound to 127.0.0.1)"
echo "  - Backend: (assuming external/backend-only running)"
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

# Kill any existing frontend processes
echo "🧹 Cleaning up existing frontend processes..."
pkill -f "next dev" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true
pkill -f "npm" 2>/dev/null || true
sleep 2

# Force kill any remaining frontend processes on port 3000
pids=$(lsof -t -iTCP:3000 2>/dev/null || true)
if [ -n "$pids" ]; then
    echo "Force-killing processes on port 3000: $pids"
    for pid in $pids; do
        kill -KILL "$pid" 2>/dev/null || true
    done
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

echo ""
echo "✅ Frontend ready!"
echo "🎨 Frontend: http://localhost:3000"
echo ""
echo "💡 Backend should be running separately (use 'gb' for backend-only)"
echo "🛑 Press Ctrl+C to stop frontend"

# Wait for interrupt
trap 'echo ""; echo "🛑 Stopping frontend..."; kill $FRONTEND_PID 2>/dev/null || true; exit 0' INT
wait
