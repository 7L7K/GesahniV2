#!/bin/bash

# Environment switching script for GesahniV2
# Usage: ./scripts/switch_env.sh [dev|staging|prod]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}  GesahniV2 Environment Switcher${NC}"
    echo -e "${BLUE}================================${NC}"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [dev|staging|prod]"
    echo ""
    echo "Available environments:"
    echo "  dev     - Development environment (localhost, HTTP, relaxed security)"
    echo "  staging - Staging environment (HTTPS, production-like security)"
    echo "  prod    - Production environment (HTTPS, strict security)"
    echo ""
    echo "Examples:"
    echo "  $0 dev     # Switch to development environment"
    echo "  $0 staging # Switch to staging environment"
    echo "  $0 prod    # Switch to production environment"
}

# Function to backup current .env if it exists
backup_env() {
    if [ -f ".env" ]; then
        local backup_name=".env.backup.$(date +%Y%m%d_%H%M%S)"
        cp .env "$backup_name"
        print_status "Backed up current .env to $backup_name"
    fi
}

# Function to switch environment
switch_environment() {
    local env=$1
    local source_file="env.$env"
    
    print_header
    
    # Check if source file exists
    if [ ! -f "$source_file" ]; then
        print_error "Environment file '$source_file' not found!"
        echo "Available environment files:"
        ls -la env.* 2>/dev/null || echo "No environment files found"
        exit 1
    fi
    
    # Backup current .env
    backup_env
    
    # Copy the environment file to .env
    cp "$source_file" .env
    
    print_status "Switched to $env environment"
    print_status "Source: $source_file"
    print_status "Target: .env"
    
    # Show key differences for the environment
    echo ""
    print_status "Environment-specific settings for $env:"
    echo "----------------------------------------"
    
    case $env in
        "dev")
            echo "APP_URL: http://localhost:3000"
            echo "API_URL: http://localhost:8000"
            echo "CORS_ALLOW_ORIGINS: http://localhost:3000"
            echo "COOKIE_SECURE: 0"
            echo "COOKIE_SAMESITE: lax"
            echo "DEV_MODE: 1"
            ;;
        "staging")
            echo "APP_URL: https://staging.gesahni.com"
            echo "API_URL: https://api-staging.gesahni.com"
            echo "CORS_ALLOW_ORIGINS: https://staging.gesahni.com"
            echo "COOKIE_SECURE: 1"
            echo "COOKIE_SAMESITE: lax"
            echo "DEV_MODE: 0"
            ;;
        "prod")
            echo "APP_URL: https://app.gesahni.com"
            echo "API_URL: https://api.gesahni.com"
            echo "CORS_ALLOW_ORIGINS: https://app.gesahni.com"
            echo "COOKIE_SECURE: 1"
            echo "COOKIE_SAMESITE: strict"
            echo "DEV_MODE: 0"
            ;;
    esac
    
    echo ""
    print_warning "Remember to:"
    echo "  1. Set your API keys and secrets in .env"
    echo "  2. Update URLs to match your actual deployment"
    echo "  3. Configure your database connections"
    echo "  4. Set appropriate JWT secrets"
    
    echo ""
    print_status "Environment switch complete!"
}

# Main script logic
main() {
    # Check if environment argument is provided
    if [ $# -eq 0 ]; then
        print_error "No environment specified"
        show_usage
        exit 1
    fi
    
    local env=$1
    
    # Validate environment argument
    case $env in
        "dev"|"staging"|"prod")
            switch_environment "$env"
            ;;
        *)
            print_error "Invalid environment: $env"
            show_usage
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
