# Test Failure Analysis - Baseline

## Executive Summary
The primary issue preventing test execution is a **circular import problem** in the router module system. This affects multiple test files and prevents comprehensive test execution.

## Failure Categories

### 🔴 Critical: ImportError / Circular Import Issues (DOMINANT - ~90% of failures)
**Root Cause**: Circular dependency between `app.router` (package) and `router` (module)

**Affected Files:**
- `tests/test_remaining_budget_fix.py`
- `tests/test_sessions_api.py`
- `tests/test_tasks.py`
- `tests/test_remaining_budget_fix.py`
- `tests/test_sessions_api.py`
- `tests/test_tasks.py`

**Error Pattern:**
```
RecursionError: maximum recursion depth exceeded
!!! Recursion detected (same locals & position)
```

**Specific Import Chain:**
1. Test imports from `app.router` (package)
2. `app/router/__init__.py` tries to import from `router` (module)
3. `router` module imports from `app.router` (creating cycle)

**Impact:** Prevents test execution entirely

### 🟡 Secondary: Missing Route Exports
**Pattern:** Tests expecting functions that aren't properly exported from router modules

**Examples:**
- `get_remaining_budget` - exists in `router.py` but not accessible via `app.router`
- `OPENAI_TIMEOUT_MS` - exists but causes import recursion
- `OLLAMA_TIMEOUT_MS` - same issue

### 🟢 Potential: Route/Method Mismatches (Cannot assess due to import failures)
**Expected Issues (based on code analysis):**
- 404 errors on `/v1/ask` endpoint conflicts
- 405 method mismatches
- CSRF validation failures
- JWT token refresh issues

## Current Status
- ✅ **Routes dumped**: 293 routes successfully extracted
- ✅ **OpenAPI exported**: 197 paths documented
- ✅ **Test collection**: 562 test files identified
- ❌ **Test execution**: Blocked by circular imports
- ❌ **Failure analysis**: Cannot run tests to analyze runtime failures

## Recommended Fix Order

### Priority 1: Fix Circular Imports (CRITICAL)
**Why:** This blocks all test execution and prevents assessing other issues

**Solution Options:**
1. **Consolidate router modules**: Merge `app/router/` package into single `router.py`
2. **Fix import paths**: Update all imports to use consistent module references
3. **Create compatibility layer**: Add proper `__init__.py` exports without circular deps

### Priority 2: Route Registration Issues
**Why:** Mismatched route definitions cause 404/405 errors

**Tasks:**
- Verify all expected routes are mounted
- Check for conflicting route prefixes
- Ensure proper method handlers are attached

### Priority 3: Authentication/CSRF Issues
**Why:** Cookie/header handshake problems affect user sessions

**Tasks:**
- Verify CSRF token validation logic
- Check JWT refresh token handling
- Validate cookie configuration consistency

### Priority 4: API Contract Mismatches
**Why:** Status code and response format discrepancies

**Tasks:**
- Compare OpenAPI spec vs actual responses
- Fix error envelope standardization
- Ensure consistent JSON response formats

## Next Steps
1. Fix circular import issue to enable test execution
2. Run focused tests on specific endpoints (`/ask`, `/google`, `/refresh`)
3. Analyze runtime failures for 404/405/500 errors
4. Address authentication and CSRF issues
5. Standardize error responses and status codes

## Metrics
- **Routes mounted**: 293
- **OpenAPI paths**: 197
- **Test files**: 562
- **Import failures**: ~10+ files affected
- **Execution blockers**: 100% (circular imports)
