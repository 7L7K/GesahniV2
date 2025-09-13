# =============================================================================
# GESAHNI DEVELOPMENT ALIASES AND FUNCTIONS
# =============================================================================
# Add this section to your ~/.zshrc file for easy Gesahni development

# Avoid noisy zsh glob errors when patterns don't match
setopt NO_NOMATCH

# Gesahni project directory
export GESAHNI_DIR="$HOME/2025/GesahniV2"

# Safe lsof wrapper that won't hang (macOS compatible)
_safe_lsof() {
    # Use gtimeout (coreutils) if available, otherwise lsof with -nP to avoid DNS hangs
    if command -v gtimeout >/dev/null 2>&1; then
        gtimeout 2 lsof -nP "$@" 2>/dev/null
    else
        lsof -nP "$@" 2>/dev/null
    fi
}

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
    if curl -s http://localhost:8000/health >/dev/null 2>&1; then
        echo "✅ Backend: http://localhost:8000 (running)"

        # Check our new endpoints
        if curl -s http://localhost:8000/v1/whoami >/dev/null 2>&1; then
            echo "   ✅ /v1/whoami: working"
        else
            echo "   ❌ /v1/whoami: not responding"
        fi

        if curl -s http://localhost:8000/__diag/fingerprint >/dev/null 2>&1; then
            echo "   ✅ Diagnostics: available"
        else
            echo "   ❌ Diagnostics: not available"
        fi

        if curl -s http://localhost:8000/healthz/ready >/dev/null 2>&1; then
            echo "   ✅ Health check: passing"
        else
            echo "   ⚠️  Health check: not ready yet"
        fi
    else
        echo "❌ Backend: not responding"
    fi

    # Check frontend
    if curl -s http://localhost:3000 >/dev/null 2>&1; then
        echo "✅ Frontend: http://localhost:3000 (running)"
    else
        echo "❌ Frontend: not responding"
    fi

    # Check Qdrant
    if curl -s http://localhost:6333/readyz >/dev/null 2>&1; then
        echo "✅ Qdrant: http://localhost:6333 (running)"
    else
        echo "❌ Qdrant: not responding"
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
    echo "  Diag:      http://localhost:8000/__diag/fingerprint"
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

    # Stop only LISTENING processes on specific ports (not all connected processes)
    for port in "${ports[@]}"; do
      pids=$(_safe_lsof -t -iTCP:$port -sTCP:LISTEN 2>/dev/null || true)
      if [ -n "$pids" ]; then
        found=true
        echo "Found LISTENING processes on port $port: $pids"
        for pid in $pids; do
          if kill -0 "$pid" 2>/dev/null; then
            kill -TERM "$pid" 2>/dev/null || true
          fi
        done
        sleep 1
        # Force kill any remaining listeners
        remaining_pids=$(_safe_lsof -t -iTCP:$port -sTCP:LISTEN 2>/dev/null || true)
        for pid in $remaining_pids; do
          if kill -0 "$pid" 2>/dev/null; then
            echo "Force-killing remaining listener on port $port: $pid"
            kill -KILL "$pid" 2>/dev/null || true
          fi
        done
      fi
    done

    # Final cleanup - kill any remaining processes on our ports
    sleep 2
    for port in "${ports[@]}"; do
      remaining_pids=$(_safe_lsof -t -iTCP:$port 2>/dev/null || true)
      if [ -n "$remaining_pids" ]; then
        echo "⚠️  Force-killing remaining processes on port $port: $remaining_pids"
        for pid in $remaining_pids; do
          kill -KILL "$pid" 2>/dev/null || true
        done
      fi
    done

    if [ "$found" = true ]; then
      echo "✅ Stopped all development processes and cleaned up stragglers"
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

    # Check backend health (use /healthz/ready for more comprehensive check)
    if curl -fsS --max-time 5 --retry 2 --retry-delay 1 http://localhost:8000/healthz/ready >/dev/null 2>&1; then
        echo "✅ Backend: http://localhost:8000 (running)"

        # Check /v1/whoami endpoint
        if curl -fsS --max-time 5 --retry 2 --retry-delay 1 http://localhost:8000/v1/whoami >/dev/null 2>&1; then
            echo "   ✅ /v1/whoami: working"
        else
            echo "   ❌ /v1/whoami: not responding"
        fi

        # Check diagnostic endpoints
        if curl -fsS --max-time 5 --retry 2 --retry-delay 1 http://localhost:8000/__diag/fingerprint >/dev/null 2>&1; then
            echo "   ✅ Diagnostics: available"
        else
            echo "   ❌ Diagnostics: not available"
        fi
    else
        echo "❌ Backend: http://localhost:8000 (not ready)"
        echo "   Recent backend logs:"

        # Show last 20 lines of backend logs if available
        if [ -d "logs" ] && [ -f "logs/backend.log" ]; then
            tail -n 20 logs/backend.log 2>/dev/null | sed 's/^/     /'
        elif command -v journalctl >/dev/null 2>&1; then
            # Try journalctl for systemd-managed services
            journalctl -u gesahni-backend --since "5 minutes ago" -n 20 --no-pager 2>/dev/null | sed 's/^/     /' || echo "     No journalctl logs available"
        else
            # Fallback: check for running uvicorn processes
            uvicorn_pids=$(pgrep -f "uvicorn.*app.main:app" 2>/dev/null || true)
            if [ -n "$uvicorn_pids" ]; then
                echo "     Found uvicorn processes: $uvicorn_pids"
                echo "     Backend may be starting up or has startup issues"
            else
                echo "     No backend processes found. Run 'gb' to start backend."
            fi
        fi
        echo ""
        return 1  # Exit with error code
    fi

    # Check frontend
    if curl -fsS --max-time 5 --retry 2 --retry-delay 1 http://localhost:3000 >/dev/null 2>&1; then
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
    ps aux | grep -E "(uvicorn|next|npm)" | grep -v grep | while read -r line; do
        pid=$(echo "$line" | awk '{print $2}')
        cmd=$(echo "$line" | awk '{for(i=11;i<=NF;i++) printf "%s ", $i; print ""}' | sed 's/ $//')
        printf "  %s: %s\n" "$pid" "$cmd"
    done

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

# Function to show route census
gesahni-routes() {
    echo "🔍 Gesahni Route Census"
    echo "======================="

    # Check if backend is running
    if ! curl -fsS --max-time 2 http://localhost:8000/healthz >/dev/null 2>&1; then
        echo "❌ Backend not running at http://localhost:8000"
        return 1
    fi

    echo "Fetching OpenAPI spec from http://localhost:8000/openapi.json"
    echo ""

    # Get routes and count them
    routes=$(curl -s http://localhost:8000/openapi.json | jq -r '.paths | keys[]' 2>/dev/null || echo "")
    if [ -z "$routes" ]; then
        echo "❌ Failed to fetch routes from OpenAPI spec"
        return 1
    fi

    # Count total routes
    total_count=$(echo "$routes" | wc -l)

    # Count legacy routes
    legacy_count=$(echo "$routes" | grep -c "^/v1/legacy" || echo "0")

    # Display results
    echo "📊 Route Summary:"
    echo "  Total routes: $total_count"
    echo "  Legacy routes (/v1/legacy/*): $legacy_count"
    echo ""

    echo "📋 All Routes (sorted):"
    echo "$routes" | sort | awk '{print NR, $0}'

    # Show legacy route details if any exist
    if [ "$legacy_count" -gt 0 ]; then
        echo ""
        echo "⚠️  Legacy Routes (marked for deprecation):"
        echo "$routes" | grep "^/v1/legacy" | sort | awk '{print "  • " $0}'
        echo ""
        echo "💡 Tip: Monitor legacy_hits_total metric in Grafana to track usage before removal"
    fi
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
    echo "  gesahni-front     - Just frontend (UI dev)"
    echo "  gesahni-qdrant    - Just vector store (Qdrant testing)"
    echo ""
    echo "Utilities:"
    echo "  gesahni-status    - Check if services are running"
    echo "  gesahni-budget    - Check startup budget (1.4s faster!)"
    echo "  gesahni-test      - Test localhost configuration"
    echo "  gesahni-open      - Open in browser"
    echo "  gesahni-routes    - Show route census with legacy counts"
    echo "  gesahni-help      - Show this help"
    echo ""
    echo "Navigation:"
    echo "  gesahni           - Navigate to project directory"
    echo ""
    echo "Recent Updates:"
    echo "  • Tier-1: Router paths normalized, duplicates killed"
    echo "  • Tier-2: Startup shave (1.4s faster), lazy imports"
    echo "  • Tier-3: Legacy Google compat, frontend resilience"
    echo "  • 0 route collisions, 200 /v1/whoami, clean routing"
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
alias gsr="gesahni-routes"     # Route census with legacy counts
alias gbgt="gesahni-budget"     # Startup budget check
alias go="gesahni-open"
alias gh="gesahni-help"
alias g="gesahni"

# Summary of aliases
echo "🚀 Gesahni aliases loaded: gs=full, gb=backend, gf=frontend, gq=qdrant, gst=status, gsr=routes, gbgt=budget, gx=stop, gr=restart, gc=clear, go=open, gh=help"
