# =============================================================================
# GESAHNI DEVELOPMENT COMMANDS
# =============================================================================

# Gesahni project directory
export GESAHNI_DIR="$HOME/2025/GesahniV2"

# Navigate to Gesahni project
alias g="cd $GESAHNI_DIR"

# Full orchestra (Qdrant + backend + frontend)
alias gs="cd $GESAHNI_DIR && ./scripts/start.sh"

# Stop all development processes
alias gx="cd $GESAHNI_DIR && ./scripts/stop.sh"

# Restart both services
alias gr="cd $GESAHNI_DIR && ./scripts/restart.sh"

# Clear cookies and restart fresh
alias gc="cd $GESAHNI_DIR && ./scripts/clear-cookies.sh"

# Test localhost configuration
alias gt="cd $GESAHNI_DIR && ./scripts/test-localhost.sh"

# Just backend (API debugging)
alias gb="cd $GESAHNI_DIR && ./scripts/backend-only.sh"

# Just frontend (UI dev)
alias gf="cd $GESAHNI_DIR && ./scripts/frontend-only.sh"

# Just vector store (Qdrant testing)
alias gq="cd $GESAHNI_DIR && ./scripts/qdrant-only.sh"

# Check status
alias gst="echo '🔍 Checking Gesahni Status...' && curl -s http://localhost:8000/healthz/ready >/dev/null && echo '✅ Backend: running' || echo '❌ Backend: not running' && curl -s http://localhost:3000 >/dev/null && echo '✅ Frontend: running' || echo '❌ Frontend: not running'"

# Open in browser
alias go="open http://localhost:3000 && open http://localhost:8000/docs"

# Show help
alias gh="echo '🚀 Gesahni Commands: gs=full, gb=backend, gf=frontend, gq=qdrant, gx=stop, gr=restart, gc=clear, gst=status, go=open, gh=help'"
