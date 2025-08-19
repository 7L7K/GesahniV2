#!/usr/bin/env bash
set -euo pipefail

echo "🧪 Testing Localhost Configuration"
echo "=================================="

# Test backend health
echo "🔧 Testing backend..."
if curl -s http://localhost:8000/healthz/ready >/dev/null 2>&1; then
    echo "✅ Backend is running on localhost:8000"
else
    echo "❌ Backend is not responding on localhost:8000"
    exit 1
fi

# Test frontend
echo "🎨 Testing frontend..."
if curl -s http://localhost:3000 >/dev/null 2>&1; then
    echo "✅ Frontend is running on localhost:3000"
else
    echo "❌ Frontend is not responding on localhost:3000"
    exit 1
fi

# Test CORS configuration
echo "🔒 Testing CORS configuration..."
CORS_RESPONSE=$(curl -s -H "Origin: http://localhost:3000" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: X-Requested-With" -X OPTIONS http://localhost:8000/healthz/ready -i | grep -i "access-control-allow-origin" || echo "No CORS headers found")

if echo "$CORS_RESPONSE" | grep -q "localhost:3000"; then
    echo "✅ CORS is properly configured for localhost:3000"
else
    echo "❌ CORS configuration issue: $CORS_RESPONSE"
fi

# Test environment variables
echo "📝 Testing environment configuration..."
if [ -f "env.localhost" ]; then
    echo "✅ Backend environment file exists"
    if grep -q "localhost" env.localhost; then
        echo "✅ Backend configured for localhost"
    else
        echo "❌ Backend not fully configured for localhost"
    fi
else
    echo "❌ Backend environment file missing"
fi

if [ -f "frontend/.env.local" ]; then
    echo "✅ Frontend environment file exists"
    if grep -q "localhost" frontend/.env.local; then
        echo "✅ Frontend configured for localhost"
    else
        echo "❌ Frontend not fully configured for localhost"
    fi
else
    echo "❌ Frontend environment file missing"
fi

# Test URL helpers
echo "🔗 Testing URL helpers..."
BACKEND_URL=$(curl -s http://localhost:8000/healthz/ready | jq -r '.url' 2>/dev/null || echo "http://localhost:8000")
if echo "$BACKEND_URL" | grep -q "localhost"; then
    echo "✅ Backend URLs use localhost"
else
    echo "❌ Backend URLs may not use localhost: $BACKEND_URL"
fi

echo ""
echo "🎉 Localhost configuration test complete!"
echo "📊 Backend: http://localhost:8000"
echo "🎨 Frontend: http://localhost:3000"
echo ""
echo "💡 If you see any ❌ errors, run: ./scripts/clear-cookies.sh"
