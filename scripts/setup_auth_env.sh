#!/bin/bash
# Setup script for authentication environment
# This ensures all required environment variables are set for auth to work

set -e

echo "🔧 Setting up authentication environment..."

# Create minimal .env file if it doesn't exist or is empty
if [ ! -f .env ] || [ ! -s .env ]; then
    echo "📝 Creating minimal .env file with authentication defaults..."
    cat > .env << 'EOF'
# Authentication Configuration
CSRF_ENABLED=1
JWT_SECRET=test-secret-key-for-development-only-change-in-production

# Development settings
DEV_MODE=1
COOKIE_SECURE=0
COOKIE_SAMESITE=lax

# CORS for frontend
CORS_ALLOW_ORIGINS=http://localhost:3000
CORS_ALLOW_CREDENTIALS=false

# Basic server config
HOST=localhost
PORT=8000

# Optional: Admin token for config endpoints
ADMIN_TOKEN=dev-admin-token
EOF
    echo "✅ Created minimal .env file"
else
    echo "ℹ️  .env file already exists with content, preserving it..."

    # Only add missing critical settings
    if ! grep -q "CSRF_ENABLED=" .env; then
        echo "⚠️  CSRF_ENABLED not set, adding..."
        echo "CSRF_ENABLED=1" >> .env
    fi

    if ! grep -q "JWT_SECRET=" .env || grep -q "JWT_SECRET=$" .env; then
        echo "⚠️  JWT_SECRET not set, adding..."
        echo "JWT_SECRET=test-secret-key-for-development-only-change-in-production" >> .env
    fi

    if ! grep -q "DEV_MODE=" .env; then
        echo "⚠️  DEV_MODE not set, adding..."
        echo "DEV_MODE=1" >> .env
    fi

    echo "✅ Preserved existing .env file with critical auth settings"
fi

echo "✅ Authentication environment setup complete!"
echo ""
echo "📋 Environment variables configured:"
echo "   • CSRF_ENABLED=1 (enables CSRF protection)"
echo "   • JWT_SECRET=*** (set for JWT token generation)"
echo "   • DEV_MODE=1 (development-friendly settings)"
echo "   • COOKIE_SECURE=0 (allows HTTP cookies in dev)"
echo ""
echo "🚀 You can now run the server with: uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
echo "🧪 Test authentication with: bash scripts/test_auth_smoke.sh"
