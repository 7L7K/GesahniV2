# =============================================================================
# GESAHNI DEVELOPMENT ALIASES AND FUNCTIONS
# =============================================================================
# Add this section to your ~/.zshrc file for easy Gesahni development

# Avoid noisy zsh glob errors when patterns don't match
setopt NO_NOMATCH 2>/dev/null || true

# Gesahni project directory
export GESAHNI_DIR="$HOME/2025/GesahniV2"

# Function to navigate to Gesahni project
gesahni() {
    cd "$GESAHNI_DIR"
}

# Function to start Gesahni development environment
gesahni-start() {
    cd "$GESAHNI_DIR"
    ./scripts/start.sh
}

# Function to stop Gesahni development environment
gesahni-stop() {
    cd "$GESAHNI_DIR"

    echo "🛑 Stopping Gesahni Development Environment"

    patterns=("uvicorn app.main:app" "next dev" "pnpm dev" "npm run dev")
    ports=(8000 3000)

    found=false

    # Stop by process pattern
    for pat in "${patterns[@]}"; do
      pids=$(pgrep -f -- "$pat" || true)
      if [ -n "$pids" ]; then
        found=true
        echo "Found processes for '$pat': $pids"
        for pid in $pids; do
          if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
          fi
        done
        sleep 1
        for pid in $pids; do
          if kill -0 "$pid" 2>/dev/null; then
            echo "Forcing kill PID $pid"
            kill -KILL "$pid" 2>/dev/null || true
          fi
        done
      fi
    done

    # Stop by ports (if any process is listening)
    for port in "${ports[@]}"; do
      pids=$(lsof -t -iTCP:$port -sTCP:LISTEN 2>/dev/null || true)
      if [ -n "$pids" ]; then
        found=true
        echo "Found listeners on port $port: $pids"
        for pid in $pids; do
          if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
          fi
        done
        sleep 1
        for pid in $pids; do
          if kill -0 "$pid" 2>/dev/null; then
            echo "Forcing kill PID $pid"
            kill -KILL "$pid" 2>/dev/null || true
          fi
        done
      fi
    done

    if [ "$found" = true ]; then
      echo "✅ Stopped matching development processes"
    else
      echo "ℹ️  No matching development processes found"
    fi
}

# Function to restart Gesahni development environment
gesahni-restart() {
    cd "$GESAHNI_DIR"
    ./scripts/restart.sh
}

# Function to clear cookies and restart fresh
gesahni-clear() {
    cd "$GESAHNI_DIR"
    ./scripts/clear-cookies.sh
}

# Function to test localhost configuration
gesahni-test() {
    cd "$GESAHNI_DIR"
    ./scripts/test-localhost.sh
}

# Function to start only backend
gesahni-back() {
    cd "$GESAHNI_DIR"
    source .venv/bin/activate
    uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
}

# Function to start only frontend
gesahni-front() {
    cd "$GESAHNI_DIR/frontend"
    unset PORT
    npm run dev
}

# Function to check Gesahni status
gesahni-status() {
    echo "🔍 Checking Gesahni Development Status"
    echo "====================================="

    # Check backend
    if curl -s http://localhost:8000/healthz/ready >/dev/null 2>&1; then
        echo "✅ Backend: http://localhost:8000 (running)"
    else
        echo "❌ Backend: http://localhost:8000 (not running)"
    fi

    # Check frontend
    if curl -s http://localhost:3000 >/dev/null 2>&1; then
        echo "✅ Frontend: http://localhost:3000 (running)"
    else
        echo "❌ Frontend: http://localhost:3000 (not running)"
    fi

    # Check processes
    echo ""
    echo "📊 Active Processes:"
    ps aux | grep -E "(uvicorn|next|npm)" | grep -v grep | awk '{print "  " $11 " " $12 " " $13}'
}

# Function to open Gesahni in browser
gesahni-open() {
    open http://localhost:3000
    open http://localhost:8000/docs
}

# Function to show Gesahni help
gesahni-help() {
    echo "🚀 Gesahni Development Commands"
    echo "==============================="
    echo ""
    echo "Quick Start:"
    echo "  gesahni-start     - Start both backend and frontend"
    echo "  gesahni-stop      - Stop all development processes"
    echo "  gesahni-restart   - Restart both services"
    echo "  gesahni-clear     - Clear cookies and restart fresh"
    echo ""
    echo "Individual Services:"
    echo "  gesahni-back      - Start only backend"
    echo "  gesahni-front     - Start only frontend"
    echo ""
    echo "Utilities:"
    echo "  gesahni-status    - Check if services are running"
    echo "  gesahni-test      - Test localhost configuration"
    echo "  gesahni-open      - Open in browser"
    echo "  gesahni-help      - Show this help"
    echo ""
    echo "Navigation:"
    echo "  gesahni           - Navigate to project directory"
    echo ""
    echo "URLs:"
    echo "  Frontend: http://localhost:3000"
    echo "  Backend:  http://localhost:8000"
    echo "  API Docs: http://localhost:8000/docs"
    echo "  Health:   http://localhost:8000/healthz/ready"
}

# Aliases for quick access
alias gs="gesahni-start"
alias gx="gesahni-stop"
alias gr="gesahni-restart"
alias gc="gesahni-clear"
alias gt="gesahni-test"
alias gb="gesahni-back"
alias gf="gesahni-front"
alias gst="gesahni-status"
alias go="gesahni-open"
alias gh="gesahni-help"
alias g="gesahni"

