#!/bin/bash
set -e

# CI Integration for Startup Budget Check
# Runs PYTHONPROFILEIMPORTTIME and enforces startup budgets

echo "🏃 Starting startup budget check..."

# Set environment for CI if not already set
export ENV=${ENV:-ci}

# Run the import with profiling
echo "📊 Profiling imports..."
PYTHONPROFILEIMPORTTIME=1 python -c "import app.main" 2>&1 | python scripts/check_startup_budget.py

echo "✅ Startup budget check completed successfully"
