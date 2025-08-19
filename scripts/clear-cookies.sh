#!/usr/bin/env bash
set -euo pipefail

echo "🧹 Clearing Cookies and Restarting Fresh"
echo "========================================"

# Kill any existing processes
echo "🛑 Stopping existing processes..."
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "pnpm dev" 2>/dev/null || true
sleep 2

# Clear browser cookies for localhost
echo "🍪 Clearing browser cookies for localhost..."
echo "   Please manually clear cookies for localhost:3000 and localhost:8000 in your browser"
echo "   Or use browser developer tools to clear all localhost cookies"

# Clear local storage files
echo "🗂️  Clearing local storage files..."
rm -f cookies.txt 2>/dev/null || true
rm -f sessions/* 2>/dev/null || true
rm -f data/*.json 2>/dev/null || true

# Clear frontend build cache and environment
echo "🏗️  Clearing frontend build cache..."
cd frontend
rm -rf .next 2>/dev/null || true
rm -rf node_modules/.cache 2>/dev/null || true
rm -f .env.local 2>/dev/null || true
cd ..

# Clear backend cache
echo "🔧 Clearing backend cache..."
rm -rf __pycache__ 2>/dev/null || true
find . -name "*.pyc" -delete 2>/dev/null || true
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

echo ""
echo "✅ Cleanup complete!"
echo ""
echo "🚀 Starting fresh development environment..."
echo ""

# Start the development environment
./scripts/dev.sh
