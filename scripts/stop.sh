#!/usr/bin/env bash

# Gesahni Development Stop Script
echo "🛑 Stopping Gesahni Development Environment"

# Kill all development processes
pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "pnpm dev" 2>/dev/null || true
pkill -f "npm run dev" 2>/dev/null || true

echo "✅ All development processes stopped"
