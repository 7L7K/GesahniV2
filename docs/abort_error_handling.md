# AbortError Handling in GesahniV2

## Overview

This document describes the comprehensive AbortError handling implemented across the GesahniV2 frontend codebase to properly handle cases where fetch requests are aborted, typically due to:

- CORS preflight failures
- Cookie not sent
- TLS mismatches
- Network timeouts
- User navigation away from page
- Component unmounting

## What is AbortError?

An `AbortError` is thrown when a fetch request is aborted, usually because:

1. **CORS Issues**: Preflight requests fail due to missing credentials or incorrect headers
2. **Authentication Problems**: Required cookies or tokens are not sent
3. **Network Issues**: TLS handshake failures, connection timeouts
4. **User Actions**: Navigation away from page, component unmounting
5. **Programmatic Cancellation**: AbortController signals

## Implementation Details

### 1. Utility Functions

Added to `frontend/src/lib/api.ts`:

```typescript
// Utility function to check if an error is an AbortError
function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}

// Utility function to handle AbortError gracefully
function handleAbortError(error: unknown, context: string): boolean {
  if (isAbortError(error)) {
    console.info(`${context}: Request aborted`);
    return true; // Indicates this was an AbortError
  }
  return false; // Indicates this was not an AbortError
}
```

### 2. Updated Components

#### `frontend/src/lib/api.ts`
- **tryRefresh()**: Now handles AbortError during token refresh
- **apiFetch()**: Uses utility functions for consistent error handling

#### `frontend/src/hooks/useBackendStatus.ts`
- **pollReady()**: Distinguishes between network failures and aborted requests
- **pollDeps()**: Preserves last known state when requests are aborted

#### `frontend/src/services/authOrchestrator.ts`
- **checkAuth()**: Doesn't treat aborted auth checks as authentication failures

#### `frontend/src/services/bootstrapManager.ts`
- **_performInitializationWithErrorHandling()**: Gracefully handles aborted initialization

#### `frontend/src/services/wsHub.ts`
- **connect()**: Doesn't retry WebSocket connections that were aborted

#### `frontend/src/app/page.tsx`
- **handleAuthFinish()**: Already had proper AbortError handling (existing implementation)

## Error Handling Patterns

### Pattern 1: Early Return on AbortError
```typescript
} catch (error) {
  if (handleAbortError(error, 'Context description')) {
    return; // Don't treat as error, just return
  }
  // Handle other errors normally
}
```

### Pattern 2: Preserve State on AbortError
```typescript
} catch (error) {
  if (handleAbortError(error, 'Context description')) {
    return; // Keep last known state
  }
  // Update state to error condition
}
```

### Pattern 3: Don't Retry on AbortError
```typescript
} catch (error) {
  if (handleAbortError(error, 'Context description')) {
    return; // Don't retry aborted requests
  }
  // Implement retry logic for other errors
}
```

## Testing

Added comprehensive tests in `frontend/src/lib/__tests__/api.test.ts`:

1. **Basic AbortError handling**: Verifies apiFetch properly propagates AbortError
2. **Refresh flow AbortError**: Tests AbortError handling during token refresh

### Running Tests
```bash
cd frontend
npm test -- --testPathPattern=api.test.ts --testNamePattern="AbortError"
```

## Benefits

1. **Better User Experience**: Aborted requests don't trigger unnecessary error states
2. **Reduced Log Noise**: AbortError cases are logged as info, not errors
3. **State Preservation**: Last known good state is maintained when requests are aborted
4. **No Unnecessary Retries**: Aborted requests don't trigger retry mechanisms
5. **Consistent Handling**: All components use the same AbortError detection logic

## Common Scenarios

### Scenario 1: User Navigates Away During Request
- **Before**: Request failure logged as error, state corrupted
- **After**: Request aborted gracefully, state preserved

### Scenario 2: CORS Preflight Failure
- **Before**: Generic network error, unclear cause
- **After**: AbortError detected, logged with context

### Scenario 3: Component Unmounts During Request
- **Before**: Memory leaks, error callbacks on unmounted components
- **After**: AbortError handled, no side effects

### Scenario 4: Network Timeout
- **Before**: Request appears to fail, unclear if retry is appropriate
- **After**: AbortError detected, can distinguish from actual failures

## Future Improvements

1. **AbortController Integration**: Use AbortController for all requests to enable proper cancellation
2. **Timeout Handling**: Implement request timeouts that trigger AbortError
3. **Retry Logic**: Implement smart retry logic that doesn't retry on AbortError
4. **Metrics**: Track AbortError frequency to identify problematic endpoints

## Related Documentation

- [Authentication Architecture](./auth_centralized_architecture.md)
- [CORS and CSRF Troubleshooting](../CORS_CSRF_TROUBLESHOOTING.md)
- [API Error Handling](./api_error_handling.md)
