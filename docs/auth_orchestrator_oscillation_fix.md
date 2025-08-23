# Auth Orchestrator Oscillation Prevention

## Problem Description

The frontend auth orchestrator was experiencing oscillation loops where:
- `whoamiOk` state would flip between `true`/`false` rapidly
- Multiple rapid `/v1/whoami` calls were being made
- Rate limiting would kick in, causing more failures
- This created a feedback loop of increasing failures

## Root Causes Identified

1. **Multiple triggers for auth checks**: The auth orchestrator was called from multiple places (login page, wsHub, auth events, etc.)
2. **State inconsistency**: The `whoamiOk` state logic was updating on every call, not just when session readiness changed
3. **Rate limiting feedback**: When rate limiting kicked in, it caused failures which triggered more calls
4. **Event-driven triggers**: Multiple auth events could trigger rapid successive calls
5. **No debouncing**: Rapid successive calls were not being debounced

## Solution Implementation

### 1. Debouncing Mechanism

Added a 500ms debounce delay for rapid successive calls:

```typescript
private readonly DEBOUNCE_DELAY = 500; // 500ms debounce for rapid calls
private pendingAuthCheck: Promise<void> | null = null;
private debounceTimer: NodeJS.Timeout | null = null;
```

### 2. Promise Sharing

Concurrent calls now return the same promise to prevent duplicate API calls:

```typescript
async checkAuth(): Promise<void> {
    // If there's already a pending auth check, return that promise
    if (this.pendingAuthCheck) {
        console.info('AUTH Orchestrator: Auth check already pending, returning existing promise');
        return this.pendingAuthCheck;
    }
    // ... rest of implementation
}
```

### 3. Oscillation Detection

Added intelligent oscillation detection that monitors rapid state changes:

```typescript
private detectOscillation(prevState: AuthState, newState: AuthState): boolean {
    // Only detect oscillation if we have a last successful state to compare against
    if (!this.lastSuccessfulState) {
        return false;
    }

    // Don't detect oscillation during initial state setup
    if (prevState.lastChecked === 0) {
        return false;
    }

    // Check for rapid whoamiOk flips
    if (prevState.whoamiOk !== newState.whoamiOk) {
        const timeSinceLastChange = Date.now() - this.lastWhoamiCall;
        return timeSinceLastChange < 5000; // 5 seconds threshold for oscillation
    }

    // Check for rapid authentication state changes
    if (prevState.isAuthenticated !== newState.isAuthenticated ||
        prevState.sessionReady !== newState.sessionReady) {
        const timeSinceLastChange = Date.now() - this.lastWhoamiCall;
        return timeSinceLastChange < 3000; // 3 seconds threshold for auth state oscillation
    }

    return false;
}
```

### 4. Extended Backoff for Oscillation

When oscillation is detected, apply extended backoff:

```typescript
private applyOscillationBackoff(): void {
    // Apply extended backoff when oscillation is detected
    const extendedBackoff = Math.min(this.MAX_BACKOFF * 2, 60000); // Up to 60 seconds
    this.backoffUntil = Date.now() + extendedBackoff;
    this.oscillationDetectionCount = 0; // Reset counter
    console.warn(`AUTH Orchestrator: Applied oscillation backoff for ${extendedBackoff}ms`);
}
```

### 5. Improved State Management

Enhanced state management to prevent unnecessary updates:

```typescript
// Stable whoamiOk state - reflects JWT validity (sessionReady)
// Only update if session readiness actually changed to prevent oscillation
let whoamiOk = this.state.whoamiOk;
if (sessionReady !== this.state.sessionReady) {
    whoamiOk = sessionReady;
    console.info(`AUTH Orchestrator: Session readiness changed from ${this.state.sessionReady} to ${sessionReady}, whoamiOk: ${whoamiOk}`);
}
```

### 6. Better Cleanup

Enhanced cleanup to prevent memory leaks and pending operations:

```typescript
cleanup(): void {
    console.info('AUTH Orchestrator: Cleaning up');
    this.subscribers.clear();
    this.initialized = false;
    this.consecutiveFailures = 0;
    this.backoffUntil = 0;
    this.oscillationDetectionCount = 0;
    this.lastSuccessfulState = null;

    // Clear any pending operations
    if (this.debounceTimer) {
        clearTimeout(this.debounceTimer);
        this.debounceTimer = null;
    }
    this.pendingAuthCheck = null;
}
```

## Key Features

### 1. Debouncing
- 500ms debounce delay for rapid calls
- Prevents multiple API calls for the same operation

### 2. Promise Sharing
- Concurrent calls return the same promise
- Prevents duplicate API calls during rapid successive calls

### 3. Oscillation Detection
- Monitors rapid state changes
- 5-second threshold for `whoamiOk` flips
- 3-second threshold for auth state changes
- Only triggers after initialization and with successful state history

### 4. Extended Backoff
- Up to 60 seconds of backoff when oscillation is detected
- Resets oscillation counter on successful calls

### 5. Rate Limiting Integration
- Proper handling of HTTP 429 responses
- Exponential backoff with jitter
- Resets failure count on successful calls

### 6. State Stability
- `whoamiOk` only updates when session readiness actually changes
- Prevents unnecessary state updates that could trigger oscillation

## Configuration

The oscillation prevention can be configured through these constants:

```typescript
private readonly MIN_CALL_INTERVAL = 2000; // 2 seconds minimum between calls
private readonly MAX_BACKOFF = 30000; // 30 seconds max backoff
private readonly BASE_BACKOFF = 1000; // 1 second base backoff
private readonly DEBOUNCE_DELAY = 500; // 500ms debounce for rapid calls
private readonly MAX_OSCILLATION_COUNT = 3; // Max rapid state changes before backoff
```

## Testing

Comprehensive tests have been created to verify:
- Debouncing of rapid calls
- Oscillation detection
- Rate limiting integration
- State stability
- Cleanup operations

## Benefits

1. **Prevents oscillation loops**: The auth orchestrator no longer gets stuck in rapid state flipping
2. **Reduces API calls**: Debouncing and promise sharing significantly reduce unnecessary API calls
3. **Better rate limiting handling**: Proper backoff prevents rate limiting feedback loops
4. **Improved stability**: State changes are more predictable and stable
5. **Better error recovery**: Extended backoff allows the system to recover from oscillation

## Monitoring

The implementation includes comprehensive logging:
- Oscillation detection warnings
- Extended backoff notifications
- Rate limiting warnings
- State change logging

This allows for monitoring and debugging of auth orchestrator behavior in production.

## Future Improvements

1. **Metrics collection**: Add metrics for oscillation detection and backoff events
2. **Dynamic thresholds**: Adjust oscillation thresholds based on system load
3. **Circuit breaker pattern**: Implement circuit breaker for repeated failures
4. **Health checks**: Add health check endpoints to monitor auth orchestrator state
