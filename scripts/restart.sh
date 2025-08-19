#!/usr/bin/env bash

# Gesahni Development Restart Script
echo "🔄 Restarting Gesahni Development Environment"

# Stop first
./scripts/stop.sh

# Wait a moment
sleep 2

# Start again
./scripts/start.sh
