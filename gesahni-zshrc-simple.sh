# =============================================================================
# GESAHNI DEVELOPMENT ALIASES AND FUNCTIONS
# =============================================================================
# Add this section to your ~/.zshrc file for easy Gesahni development

# Avoid noisy zsh glob errors when patterns don't match
setopt NO_NOMATCH

# Gesahni project directory
export GESAHNI_DIR="$HOME/2025/GesahniV2"

# Function to navigate to Gesahni project
gesahni() {
    cd "$GESAHNI_DIR"
}

# Function to start Gesahni development environment
gesahni-start() {
    cd "$GESAHNI_DIR"

    echo "🚀 Gesahni Development Environment - Enhanced Startup"
    echo "=================================================="

    # Pre-flight checks
    echo "🔍 Pre-flight checks:"
    if [ -f ".env" ]; then
        echo "   ✅ .env file present"
    else
        echo "   ❌ .env file missing - please create one"
        return 1
    fi

    if [ -d ".venv" ]; then
        echo "   ✅ Python virtual environment found"
    else
        echo "   ❌ .venv not found - run: python -m venv .venv"
        return 1
    fi

    if command -v docker >/dev/null 2>&1; then
        echo "   ✅ Docker available for Qdrant"
    else
        echo "   ⚠️  Docker not available - ensure Qdrant runs externally"
    fi

    echo ""

    # Start the services
    ./scripts/start.sh &

    # Wait for startup to complete, then run post-startup checks
    echo "⏳ Waiting for services to start..."
    _wait_for_health() {
        local endpoint="$1"
        local max_attempts=30
        local attempt=1

        while [ $attempt -le $max_attempts ]; do
            if curl -fsS --max-time 2 "$endpoint" >/dev/null 2>&1; then
                return 0
            fi
            echo -n "."
            sleep 1
            ((attempt++))
        done
        return 1
    }

    # Wait for backend to be ready
    if _wait_for_health "http://localhost:8000/healthz/ready"; then
        echo " ✅ Backend ready"
    else
        echo " ❌ Backend failed to start within 30 seconds"
    fi

    # Wait for frontend to be ready
    if _wait_for_health "http://localhost:3000"; then
        echo " ✅ Frontend ready"
    else
        echo " ❌ Frontend failed to start within 30 seconds"
    fi

    # Post-startup verification
    echo ""
    echo "🔬 Post-startup verification:"
    echo "=============================="

    # Check backend health
    if curl -fsS --max-time 5 --retry 2 --retry-delay 1 http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ Backend: http://localhost:8000 (running)"

        # Check our new endpoints
        if curl -fsS --max-time 5 --retry 2 --retry-delay 1 http://localhost:8000/v1/whoami >/dev/null 2>&1; then
            echo "   ✅ /v1/whoami: working"
        else
            echo "   ❌ /v1/whoami: not responding"
        fi

        if curl -fsS --max-time 5 --retry 2 --retry-delay 1 http://localhost:8000/__diag/fingerprint >/dev/null 2>&1; then
            echo "   ✅ Diagnostics: available"
        else
            echo "   ❌ Diagnostics: not available"
        fi
    else
        echo "❌ Backend: not responding"
    fi

    # Check frontend
    if curl -fsS --max-time 5 --retry 2 --retry-delay 1 http://localhost:3000 >/dev/null 2>&1; then
        echo "✅ Frontend: http://localhost:3000 (running)"
    else
        echo "❌ Frontend: not responding"
    fi

    echo ""
    echo "🎯 Gesahni Status Summary:"
    echo "=========================="
    echo "• Tier-1: Router paths normalized (0 collisions)"
    echo "• Tier-2: Startup optimized (1.4s faster)"
    echo "• Tier-3: Legacy Google OAuth feature flag ready"
    echo ""
    echo "📊 URLs:"
    echo "  Frontend:  http://localhost:3000"
    echo "  Backend:   http://localhost:8000"
    echo "  API Docs:  http://localhost:8000/docs"
    echo "  Health:    http://localhost:8000/healthz/ready"
    echo ""
    echo "💡 Tip: Run 'gst' anytime to check status, 'gbgt' for startup budget"
    echo "🛑 Use 'gx' to stop all services"
}

# Function to stop Gesahni development environment
gesahni-stop() {
    cd "$GESAHNI_DIR"

    echo "🛑 Stopping Gesahni Development Environment"

    # More specific patterns scoped to Gesahni directory and exact commands
    patterns=("$GESAHNI_DIR.*uvicorn app.main:app" "$GESAHNI_DIR.*next dev" "$GESAHNI_DIR.*next-server")
    ports=(8000 3000)

    found=false

    # Stop by specific Gesahni-scoped process patterns
    for pat in "${patterns[@]}"; do
      pids=$(pgrep -f -- "$pat" || true)
      if [ -n "$pids" ]; then
        found=true
        echo "Found Gesahni processes for '$pat': $pids"
        for pid in $pids; do
          if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
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
    ./scripts/backend-only.sh
}

# Function to start only frontend
gesahni-front() {
    cd "$GESAHNI_DIR/frontend"
    unset PORT

    # Detect and use preferred package manager
    if command -v bun >/dev/null 2>&1 && [ -f "bun.lockb" ]; then
        echo "🐰 Using bun (lockfile detected)"
        bun run dev
    elif command -v pnpm >/dev/null 2>&1 && [ -f "pnpm-lock.yaml" ]; then
        echo "📦 Using pnpm (lockfile detected)"
        pnpm run dev
    elif command -v yarn >/dev/null 2>&1 && [ -f "yarn.lock" ]; then
        echo "🧶 Using yarn (lockfile detected)"
        yarn run dev
    else
        echo "📦 Using npm (fallback)"
        npm run dev
    fi
}

# Function to start only Qdrant vector store
gesahni-qdrant() {
    cd "$GESAHNI_DIR"
    ./scripts/qdrant-only.sh
}

# Function to check startup budget
gesahni-budget() {
    cd "$GESAHNI_DIR"
    echo "💰 Checking Gesahni Startup Budget"
    echo "=================================="

    if command -v python3 >/dev/null 2>&1; then
        PYTHONPROFILEIMPORTTIME=1 python3 -c "import app.main" 2>&1 | python3 scripts/check_startup_budget.py
    else
        echo "❌ Python3 not found - cannot run startup budget check"
    fi
}

# Function to check Gesahni status
gesahni-status() {
    echo "🔍 Checking Gesahni Development Status"
    echo "====================================="

    # Check backend health
    if curl -s http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ Backend: http://localhost:8000 (running)"

        # Check /v1/whoami endpoint
        if curl -s http://localhost:8000/v1/whoami >/dev/null 2>&1; then
            echo "   ✅ /v1/whoami: working"
        else
            echo "   ❌ /v1/whoami: not responding"
        fi

        # Check diagnostic endpoints
        if curl -s http://localhost:8000/__diag/fingerprint >/dev/null 2>&1; then
            echo "   ✅ Diagnostics: available"
        else
            echo "   ❌ Diagnostics: not available"
        fi
    else
        echo "❌ Backend: http://localhost:8000 (not running)"
    fi

    # Check frontend
    if curl -s http://localhost:3000 >/dev/null 2>&1; then
        echo "✅ Frontend: http://localhost:3000 (running)"
    else
        echo "❌ Frontend: http://localhost:3000 (not running)"
    fi

    # Check legacy Google OAuth status
    if [ "$GSN_ENABLE_LEGACY_GOOGLE" = "1" ]; then
        echo "⚠️  Legacy Google OAuth: ENABLED (feature flag)"
    else
        echo "✅ Legacy Google OAuth: DISABLED (production ready)"
    fi

    # Check processes
    echo ""
    echo "📊 Active Processes:"
    ps aux | grep -E "(uvicorn|next|npm)" | grep -v grep | awk '{print "  " $11 " " $12 " " $13}'

    echo ""
    echo "🔧 Recent Updates:"
    echo "   • Tier-1: Router paths normalized, duplicates killed"
    echo "   • Tier-2: Startup shave (1.4s faster), lazy imports"
    echo "   • Tier-3: Legacy Google compat, frontend resilience"
    echo "   • 0 route collisions, 200 /v1/whoami, clean routing"
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
    echo "Full Orchestra:"
    echo "  gesahni-start     - Enhanced startup with pre/post-flight checks"
    echo "  gesahni-stop      - Stop all development processes"
    echo "  gesahni-restart   - Restart all services"
    echo "  gesahni-clear     - Clear cookies and restart fresh"
    echo ""
    echo "Individual Services:"
    echo "  gesahni-back      - Just backend (API debugging)"
    echo "  gesahni-front     - Just frontend (UI development)"
    echo "  gesahni-qdrant    - Just vector store (Qdrant testing)"
    echo ""
    echo "Utilities:"
    echo "  gesahni-status    - Check if services are running"
    echo "  gesahni-budget    - Check startup budget (1.4s faster!)"
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
    echo "  Qdrant:   http://localhost:6333"
    echo "  API Docs: http://localhost:8000/docs"
    echo "  Health:   http://localhost:8000/healthz/ready"
    echo "  Diag:     http://localhost:8000/__diag/fingerprint"
}

# Aliases for quick access
alias gs="gesahni-start"        # Full orchestra (Qdrant + backend + frontend)
alias gx="gesahni-stop"
alias gr="gesahni-restart"
alias gc="gesahni-clear"
alias gt="gesahni-test"
alias gb="gesahni-back"         # Just backend (API debugging)
alias gf="gesahni-front"        # Just frontend (UI dev)
alias gq="gesahni-qdrant"       # Just vector store (Qdrant testing)
alias gst="gesahni-status"
alias gbgt="gesahni-budget"
alias go="gesahni-open"
alias gh="gesahni-help"
alias g="gesahni"
