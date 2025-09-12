#!/bin/bash
# Migration guard: fails CI if any docs or code introduce /login?next= patterns
#
# This script searches for forbidden patterns that should be replaced with
# cookie-based redirect patterns (gs_next cookie).
#
# Usage: ./tools/grep_guard.sh [--help] [--verbose] [--fix]
#
# Exit codes:
#   0: Success - no forbidden patterns found
#   1: Failure - forbidden patterns found
#   2: Error - script execution error

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default settings
VERBOSE=false
FIX_MODE=false
SEARCH_ROOT="."
EXCLUDE_PATTERNS=(
    "*.pyc"
    "__pycache__"
    ".git"
    "node_modules"
    "*.log"
    ".pytest_cache"
    "*.egg-info"
    "dist"
    "build"
    "*.min.js"
    "*.min.css"
    "vendor"
    "third_party"
    ".venv"
    "venv"
    ".env*"
)

# Forbidden patterns that should trigger failure
FORBIDDEN_PATTERNS=(
    "/login?next="
    "/v1/auth/login?next="
    "/login\?next="
    "/v1/auth/login\?next="
)

show_help() {
    cat << EOF
Migration Guard: Prevent /login?next= patterns

This script fails CI if any docs or code introduce forbidden /login?next= patterns
that should be replaced with cookie-based redirect patterns (gs_next cookie).

USAGE:
    $0 [OPTIONS]

OPTIONS:
    --help, -h          Show this help message
    --verbose, -v       Show detailed output
    --fix, -f           Show suggestions for fixing found patterns (dry-run)
    --root DIR          Search root directory (default: current directory)

EXAMPLES:
    $0                          # Basic check
    $0 --verbose               # Detailed output
    $0 --fix                   # Show fix suggestions
    $0 --root /path/to/project # Search specific directory

EXIT CODES:
    0   Success - no forbidden patterns found
    1   Failure - forbidden patterns found
    2   Error - script execution error

FORBIDDEN PATTERNS:
    /login?next=        URL-based redirect pattern
    /v1/auth/login?next= API endpoint with redirect
    /login\?next=       Escaped query pattern
    /v1/auth/login\?next= Escaped API pattern

RECOMMENDED REPLACEMENT:
    Use gs_next cookie pattern instead:
    - set_gs_next_cookie(response, path, request)
    - get_gs_next_cookie(request)
    - clear_gs_next_cookie(response, request)

EOF
}

log_verbose() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${BLUE}ℹ${NC}  $*" >&2
    fi
}

log_warning() {
    echo -e "${YELLOW}⚠${NC}  $*" >&2
}

log_error() {
    echo -e "${RED}✗${NC}  $*" >&2
}

log_success() {
    echo -e "${GREEN}✓${NC}  $*" >&2
}

build_grep_excludes() {
    local excludes=""
    for pattern in "${EXCLUDE_PATTERNS[@]}"; do
        excludes="$excludes --exclude-dir=$pattern"
    done
    echo "$excludes"
}

search_pattern() {
    local pattern="$1"
    local grep_cmd
    local excludes

    excludes=$(build_grep_excludes)
    grep_cmd="grep -r -n \"$pattern\" \"$SEARCH_ROOT\" $excludes --include=\"*.py\" --include=\"*.js\" --include=\"*.ts\" --include=\"*.tsx\" --include=\"*.md\" --include=\"*.txt\" --include=\"*.html\" --include=\"*.yml\" --include=\"*.yaml\" --include=\"*.json\""

    log_verbose "Searching for pattern: $pattern"
    log_verbose "Grep command: $grep_cmd"

    local grep_output
    local found_files=()
    local total_matches=0

    # Run grep and capture output
    if grep_output=$(eval "$grep_cmd" 2>/dev/null); then
        # Parse grep output to get unique files
        local unique_files
        unique_files=$(echo "$grep_output" | cut -d: -f1 | sort | uniq)

        # Convert to array
        while IFS= read -r file; do
            if [[ -n "$file" ]]; then
                found_files+=("$file")
                local file_matches
                file_matches=$(echo "$grep_output" | grep "^$file:" | wc -l)
                total_matches=$((total_matches + file_matches))
            fi
        done <<< "$unique_files"

        if [[ "$VERBOSE" == "true" && -n "$grep_output" ]]; then
            echo "$grep_output"
            echo
        fi
    fi

    # Return results as a single string for processing
    if [[ ${#found_files[@]} -gt 0 ]]; then
        echo "${found_files[*]}|$total_matches"
    fi
}

show_fix_suggestions() {
    local pattern="$1"
    local files="$2"

    echo -e "\n${YELLOW}💡 FIX SUGGESTIONS for pattern '$pattern':${NC}"
    echo "Replace URL-based redirects with cookie-based pattern:"
    echo
    echo "❌ AVOID:"
    echo "   /login?next=/dashboard"
    echo "   router.push('/login?next=' + encodeURIComponent(path))"
    echo
    echo "✅ USE:"
    echo "   // Set cookie for post-login redirect"
    echo "   set_gs_next_cookie(response, path, request)"
    echo "   // Then redirect to login"
    echo "   return RedirectResponse('/login', status_code=302)"
    echo
    echo "   // Or in frontend:"
    echo "   await setRedirectCookie(path)"
    echo "   router.push('/login')"
    echo
    echo "📁 Files containing this pattern:"
    echo "$files" | tr ' ' '\n' | sed 's/^/   - /'
    echo
}

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_help
                exit 0
                ;;
            --verbose|-v)
                VERBOSE=true
                shift
                ;;
            --fix|-f)
                FIX_MODE=true
                shift
                ;;
            --root)
                SEARCH_ROOT="$2"
                shift 2
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 2
                ;;
        esac
    done

    # Validate search root
    if [[ ! -d "$SEARCH_ROOT" ]]; then
        log_error "Search root directory does not exist: $SEARCH_ROOT"
        exit 2
    fi

    log_verbose "Starting migration guard scan..."
    log_verbose "Search root: $SEARCH_ROOT"
    log_verbose "Verbose mode: $VERBOSE"
    log_verbose "Fix mode: $FIX_MODE"

    local total_violations=0
    local violation_patterns=()
    local all_violation_files=()

    # Check each forbidden pattern
    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        log_verbose "Checking pattern: $pattern"

        local result
        result=$(search_pattern "$pattern")

        if [[ -n "$result" ]]; then
            # Parse result: "file1 file2|count"
            local files_part="${result%|*}"
            local count_part="${result#*|}"

            # Convert space-separated files to array
            IFS=' ' read -r -a files <<< "$files_part"

            log_warning "Found $count_part matches of '$pattern' in ${#files[@]} files"

            if [[ "$VERBOSE" == "true" ]]; then
                echo "Files:"
                printf '  - %s\n' "${files[@]}"
                echo
            fi

            violation_patterns+=("$pattern")
            all_violation_files+=("${files[@]}")
            total_violations=$((total_violations + count_part))
        else
            log_verbose "✓ No matches found for: $pattern"
        fi
    done

    # Summary and results
    echo
    if [[ $total_violations -gt 0 ]]; then
        echo -e "${RED}🚫 MIGRATION GUARD FAILURE${NC}"
        echo "Found $total_violations violations of forbidden patterns in ${#violation_patterns[@]} pattern types"
        echo
        echo "Forbidden patterns detected:"
        for pattern in "${violation_patterns[@]}"; do
            echo "  ❌ $pattern"
        done
        echo
        echo "Affected files:"
        printf '  📁 %s\n' "${all_violation_files[@]}" | sort -u
        echo

        if [[ "$FIX_MODE" == "true" ]]; then
            for pattern in "${violation_patterns[@]}"; do
                # Find files for this specific pattern
                local pattern_files=()
                for file in "${all_violation_files[@]}"; do
                    if grep -q "$pattern" "$file" 2>/dev/null; then
                        pattern_files+=("$file")
                    fi
                done

                if [[ ${#pattern_files[@]} -gt 0 ]]; then
                    show_fix_suggestions "$pattern" "${pattern_files[*]}"
                fi
            done
        fi

        echo -e "${YELLOW}💡 RECOMMENDATION:${NC}"
        echo "Replace /login?next= patterns with gs_next cookie-based redirects."
        echo "See: app/redirect_utils.py for canonical implementation."
        echo
        echo -e "${RED}CI FAILURE: Migration guard detected forbidden patterns${NC}"
        exit 1
    else
        echo -e "${GREEN}✅ MIGRATION GUARD SUCCESS${NC}"
        echo "No forbidden /login?next= patterns found"
        echo
        echo -e "${GREEN}🎉 All redirect patterns use cookie-based approach!${NC}"
        exit 0
    fi
}

# Run main function
main "$@"
