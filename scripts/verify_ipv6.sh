#!/usr/bin/env bash
set -euo pipefail

echo "🔍 Verifying IPv6 server configuration..."
echo ""

# Check if servers are running
echo "📊 Checking server status:"

# Check backend (port 8000)
echo "🔧 Backend (port 8000):"
if lsof -iTCP:8000 -sTCP:LISTEN | grep -E '::|IPv6' >/dev/null 2>&1; then
    echo "  ✅ Listening on IPv6 (::)"
    lsof -iTCP:8000 -sTCP:LISTEN | grep -E '::|IPv6'
else
    echo "  ❌ Not listening on IPv6"
    echo "  📋 Current listeners:"
    lsof -iTCP:8000 -sTCP:LISTEN 2>/dev/null || echo "    No listeners found"
fi

echo ""

# Check frontend (port 3000)
echo "🎨 Frontend (port 3000):"
if lsof -iTCP:3000 -sTCP:LISTEN | grep -E '::|IPv6' >/dev/null 2>&1; then
    echo "  ✅ Listening on IPv6 (::)"
    lsof -iTCP:3000 -sTCP:LISTEN | grep -E '::|IPv6'
else
    echo "  ❌ Not listening on IPv6"
    echo "  📋 Current listeners:"
    lsof -iTCP:3000 -sTCP:LISTEN 2>/dev/null || echo "    No listeners found"
fi

echo ""

# Test connectivity
echo "🌐 Testing connectivity:"

# Test backend
echo "🔧 Backend connectivity:"
if curl -s --connect-timeout 5 http://localhost:8000/healthz/ready >/dev/null 2>&1; then
    echo "  ✅ Backend responding on localhost"
else
    echo "  ❌ Backend not responding on localhost"
fi

# Test frontend
echo "🎨 Frontend connectivity:"
if curl -s --connect-timeout 5 http://localhost:3000 >/dev/null 2>&1; then
    echo "  ✅ Frontend responding on localhost"
else
    echo "  ❌ Frontend not responding on localhost"
fi

echo ""
echo "💡 To start servers with IPv6 support, run:"
echo "   ./scripts/dev.sh"
echo ""
echo "💡 Manual commands:"
echo "   # Backend"
echo "   uvicorn app.main:app --host :: --port 8000"
echo "   # Frontend"
echo "   cd frontend && npm run dev"
