# Authentication and Rate Limiting Fixes Summary

## Issues Identified

Based on the logs provided, several interconnected problems were causing authentication failures and rate limiting issues:

1. **Rate Limiting Oscillation**: The auth orchestrator was hitting rate limits (429 errors) due to rapid whoami calls
2. **Authentication Loop**: Music state fetch was failing with 401 errors, triggering auth refresh, which then hit rate limits
3. **WebSocket Connection Failures**: WebSocket connections were failing because authentication was not working properly
4. **Oscillation Detection**: The auth orchestrator was detecting oscillation and applying backoff, but this was causing cascading failures

## Fixes Implemented

### 1. Backend Rate Limiting Fix

**File**: `app/api/auth.py`
- **Change**: Exempted the `/v1/whoami` endpoint from rate limiting in development mode
- **Rationale**: Prevents authentication oscillation in development while maintaining security in production
- **Code**:
```python
@router.get("/whoami")
async def whoami(request: Request, _: None = Depends(rate_limit) if os.getenv("DEV_MODE", "0") != "1" else None) -> JSONResponse:
```

### 2. Auth Orchestrator Rate Limiting Improvements

**File**: `frontend/src/services/authOrchestrator.ts`

#### Increased Intervals and Backoff
- **MIN_CALL_INTERVAL**: Increased from 2000ms to 5000ms
- **MAX_BACKOFF**: Increased from 30000ms to 60000ms
- **BASE_BACKOFF**: Increased from 1000ms to 2000ms
- **DEBOUNCE_DELAY**: Increased from 500ms to 1000ms

#### Improved Oscillation Detection
- **MAX_OSCILLATION_COUNT**: Reduced from 3 to 2 to trigger backoff sooner
- **Oscillation thresholds**: Increased from 5000ms/3000ms to 10000ms/5000ms for more stable detection

#### Better Backoff Strategy
- **Exponential backoff**: Changed from 2^n to 1.5^n for gentler backoff
- **Jitter**: Reduced from ±20% to ±15% for more predictable behavior
- **Minimum backoff**: Increased from 1000ms to 2000ms

#### Special Rate Limit Handling
- **429 errors**: Now apply a special 30-second backoff instead of oscillation backoff
- **Prevents**: Rate limit errors from triggering oscillation detection

### 3. Music State Fetch Improvements

**File**: `frontend/src/app/page.tsx`

#### Reduced Retry Attempts
- **Retry limit**: Reduced from 2 to 1 retry attempt
- **Retry delay**: Increased from 1000ms to 3000ms
- **Prevents**: Excessive retries that could trigger rate limiting

#### Better Error Handling
- **Clear auth errors**: On successful music state fetch
- **Prevent oscillation**: Removed redundant auth retry logic

### 4. WebSocket Connection Improvements

**File**: `frontend/src/services/wsHub.ts`

#### Better Authentication Checks
- **Pre-connection check**: Verify authentication before attempting WebSocket connection
- **Improved error handling**: Better error messages and connection state management
- **Prevent failures**: Don't attempt connections when not authenticated

**File**: `frontend/src/app/page.tsx`

#### Conditional WebSocket Start
- **Auth state check**: Only start WebSocket connections when authenticated and session is ready
- **Prevents**: Connection attempts when authentication is unstable

## Testing

All fixes have been tested and verified:

- ✅ Auth orchestrator tests pass
- ✅ Oscillation prevention tests pass
- ✅ Rate limiting integration tests pass
- ✅ WebSocket connection tests pass

## Expected Behavior After Fixes

1. **Reduced Rate Limiting**: Whoami endpoint is exempt from rate limiting in development
2. **Stable Authentication**: Auth orchestrator uses more conservative timing to prevent oscillation
3. **Better Error Recovery**: Music state fetch retries less aggressively
4. **Proper WebSocket Connections**: Only attempt connections when properly authenticated
5. **Clear Error Messages**: Better error reporting for debugging

## Environment Variables

The fixes respect existing environment variables:
- `DEV_MODE=1`: Disables rate limiting on whoami endpoint
- `RATE_LIMIT_PER_MIN=60`: Still applies to other endpoints
- `RATE_LIMIT_BURST=10`: Still applies to other endpoints

## Backward Compatibility

All changes are backward compatible:
- Production environments (DEV_MODE=0) still have rate limiting on whoami
- Existing authentication flows continue to work
- WebSocket connections work as before when properly authenticated
- Error handling is improved but doesn't break existing functionality
