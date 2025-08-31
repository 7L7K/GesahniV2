# =============================================================================
# GESAHNI DEVELOPMENT COMMANDS
# =============================================================================

# Gesahni project directory
export GESAHNI_DIR="$HOME/2025/GesahniV2"

# Navigate to Gesahni project
alias g="cd $GESAHNI_DIR"

# Start both backend and frontend
alias gs="cd $GESAHNI_DIR && ./scripts/start.sh"

# Stop all development processes
alias gx="cd $GESAHNI_DIR && ./scripts/stop.sh"

# Restart both services
alias gr="cd $GESAHNI_DIR && ./scripts/restart.sh"

# Clear cookies and restart fresh
alias gc="cd $GESAHNI_DIR && ./scripts/clear-cookies.sh"

# Test localhost configuration
alias gt="cd $GESAHNI_DIR && ./scripts/test-localhost.sh"

# Start only backend
alias gb="cd $GESAHNI_DIR && source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"

# Start only frontend
alias gf="cd $GESAHNI_DIR/frontend && unset PORT && npm run dev"

# Check status
alias gst="echo '🔍 Checking Gesahni Status...' && curl -s http://localhost:8000/healthz/ready >/dev/null && echo '✅ Backend: running' || echo '❌ Backend: not running' && curl -s http://localhost:3000 >/dev/null && echo '✅ Frontend: running' || echo '❌ Frontend: not running'"

# Open in browser
alias go="open http://localhost:3000 && open http://localhost:8000/docs"

# Show help
alias gh="echo '🚀 Gesahni Commands: gs=start, gx=stop, gr=restart, gc=clear, gb=backend, gf=frontend, gst=status, go=open, gh=help'"
