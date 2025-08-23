#!/bin/bash

# Authentication Behavior Test Runner
#
# This script runs comprehensive tests to verify all authentication behavior requirements:
#
# Boot (logged out → logged in):
# - Load app: Network panel shows no 401 from your own APIs.
# - Sign in: finisher runs once, then exactly one whoami. authed flips once to true.
# - After auth, getMusicState runs once and succeeds.
#
# Refresh while logged in:
# - One whoami on mount, no duplicates, no flips. No component makes its own whoami.
#
# Logout:
# - Cookies cleared symmetrically. authed flips to false once. No privileged calls fire afterward.
#
# WS behavior:
# - Connect happens only when authed === true.
# - On forced WS close: one reconnect try; if it fails, UI shows "disconnected" without auth churn.
#
# Health checks:
# - After "ready: ok", polling slows down. Health calls never mutate auth state.
#
# CSP/service worker sanity:
# - whoami responses are never cached; no SW intercepts; headers show no-store.

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to run backend tests
run_backend_tests() {
    print_status "Running backend authentication behavior tests..."

    if ! command_exists python; then
        print_error "Python is not installed"
        return 1
    fi

    if ! command_exists pytest; then
        print_warning "pytest not found, installing..."
        pip install pytest pytest-asyncio
    fi

    # Set test environment variables
    export PYTEST_CURRENT_TEST="auth_behavior"
    export JWT_SECRET="test-secret-key"
    export USERS_DB=":memory:"

    # Run the backend tests
    cd "$(dirname "$0")/.."
    python -m pytest tests/test_auth_behavior.py -v --tb=short

    if [ $? -eq 0 ]; then
        print_success "Backend authentication behavior tests passed"
        return 0
    else
        print_error "Backend authentication behavior tests failed"
        return 1
    fi
}

# Function to run frontend tests
run_frontend_tests() {
    print_status "Running frontend authentication behavior tests..."

    if ! command_exists node; then
        print_error "Node.js is not installed"
        return 1
    fi

    if ! command_exists npm; then
        print_error "npm is not installed"
        return 1
    fi

    # Check if we're in the right directory
    if [ ! -f "package.json" ]; then
        print_error "package.json not found. Please run this script from the frontend directory or project root."
        return 1
    fi

    # Install dependencies if node_modules doesn't exist
    if [ ! -d "node_modules" ]; then
        print_warning "Installing frontend dependencies..."
        npm install
    fi

    # Run the frontend tests
    npm test -- --testPathPattern=authBehavior.test.tsx --verbose

    if [ $? -eq 0 ]; then
        print_success "Frontend authentication behavior tests passed"
        return 0
    else
        print_error "Frontend authentication behavior tests failed"
        return 1
    fi
}

# Function to run integration tests
run_integration_tests() {
    print_status "Running integration tests..."

    # This would run tests that verify the full stack works together
    # For now, we'll just run both backend and frontend tests
    run_backend_tests
    backend_result=$?

    run_frontend_tests
    frontend_result=$?

    if [ $backend_result -eq 0 ] && [ $frontend_result -eq 0 ]; then
        print_success "All authentication behavior tests passed"
        return 0
    else
        print_error "Some authentication behavior tests failed"
        return 1
    fi
}

# Function to check test coverage
check_coverage() {
    print_status "Checking test coverage..."

    # Backend coverage
    if command_exists coverage; then
        cd "$(dirname "$0")/.."
        coverage run -m pytest tests/test_auth_behavior.py
        coverage report --include="app/auth*,app/deps/user*,app/services/auth*"
    else
        print_warning "coverage not installed, skipping coverage report"
    fi

    # Frontend coverage
    if [ -f "package.json" ]; then
        npm test -- --coverage --testPathPattern=authBehavior.test.tsx --collectCoverageFrom="src/services/auth*,src/hooks/useAuth*,src/lib/api*"
    fi
}

# Function to show test summary
show_summary() {
    print_status "Authentication Behavior Test Summary"
    echo "=========================================="
    echo ""
    echo "Tests verify the following requirements:"
    echo ""
    echo "✅ Boot (logged out → logged in):"
    echo "   - Load app: Network panel shows no 401 from your own APIs"
    echo "   - Sign in: finisher runs once, then exactly one whoami"
    echo "   - Auth state flips once to true"
    echo "   - After auth, getMusicState runs once and succeeds"
    echo ""
    echo "✅ Refresh while logged in:"
    echo "   - One whoami on mount, no duplicates, no flips"
    echo "   - No component makes its own whoami calls"
    echo ""
    echo "✅ Logout:"
    echo "   - Cookies cleared symmetrically"
    echo "   - Auth state flips to false once"
    echo "   - No privileged calls fire afterward"
    echo ""
    echo "✅ WebSocket behavior:"
    echo "   - Connect happens only when authed === true"
    echo "   - One reconnect try on forced WS close"
    echo "   - UI shows 'disconnected' without auth churn"
    echo ""
    echo "✅ Health checks:"
    echo "   - Polling slows down after 'ready: ok'"
    echo "   - Health calls never mutate auth state"
    echo ""
    echo "✅ CSP/service worker sanity:"
    echo "   - whoami responses are never cached"
    echo "   - No service worker intercepts"
    echo "   - Headers show no-store"
    echo ""
}

# Main function
main() {
    print_status "Starting Authentication Behavior Test Suite"
    echo "=================================================="
    echo ""

    # Parse command line arguments
    case "${1:-all}" in
        "backend")
            run_backend_tests
            ;;
        "frontend")
            run_frontend_tests
            ;;
        "integration")
            run_integration_tests
            ;;
        "coverage")
            check_coverage
            ;;
        "summary")
            show_summary
            ;;
        "all")
            run_integration_tests
            ;;
        "help"|"-h"|"--help")
            echo "Usage: $0 [backend|frontend|integration|coverage|summary|all]"
            echo ""
            echo "Options:"
            echo "  backend     Run only backend authentication tests"
            echo "  frontend    Run only frontend authentication tests"
            echo "  integration Run integration tests (backend + frontend)"
            echo "  coverage    Run tests with coverage reporting"
            echo "  summary     Show test requirements summary"
            echo "  all         Run all tests (default)"
            echo "  help        Show this help message"
            echo ""
            echo "Environment Variables:"
            echo "  JWT_SECRET   Secret key for JWT tokens (default: test-secret-key)"
            echo "  USERS_DB     Database path for tests (default: :memory:)"
            echo ""
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use '$0 help' for usage information"
            exit 1
            ;;
    esac

    echo ""
    show_summary
}

# Run main function with all arguments
main "$@"
