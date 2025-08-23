# Authentication Behavior Implementation

This document provides a comprehensive overview of the authentication behavior implementation and testing approach for the Gesahni application.

## Overview

The authentication system has been designed to meet strict behavioral requirements that ensure a smooth, secure, and predictable user experience. The implementation includes both backend and frontend components with comprehensive testing to verify all requirements are met.

## Requirements Summary

The authentication behavior must satisfy these exact requirements:

### 1. Boot (logged out → logged in)
- **Load app**: Network panel shows no 401 from your own APIs
- **Sign in**: Finisher runs once, then exactly one whoami call
- **Auth state**: `authed` flips once to `true`
- **Post-auth**: `getMusicState` runs once and succeeds

### 2. Refresh while logged in
- **Mount**: One whoami on mount, no duplicates, no flips
- **Components**: No component makes its own whoami calls
- **State stability**: Auth state remains stable during refresh

### 3. Logout
- **Cookies**: Cleared symmetrically
- **Auth state**: `authed` flips to `false` once
- **Security**: No privileged calls fire afterward

### 4. WebSocket behavior
- **Connection**: Connect happens only when `authed === true`
- **Reconnection**: One reconnect try on forced WS close
- **Failure handling**: If reconnection fails, UI shows "disconnected" without auth churn

### 5. Health checks
- **Polling**: After "ready: ok", polling slows down
- **Auth isolation**: Health calls never mutate auth state

### 6. CSP/service worker sanity
- **Caching**: whoami responses are never cached
- **Service workers**: No SW intercepts
- **Headers**: Responses show `no-store` headers

## Implementation Architecture

### Backend Components

#### 1. Authentication System (`app/auth.py`)
- JWT-based authentication with access and refresh tokens
- Cookie-based session management
- Secure token validation and refresh mechanisms

#### 2. User Dependency (`app/deps/user.py`)
- Centralized user ID resolution
- Support for multiple auth sources (JWT, Clerk, cookies)
- WebSocket authentication support

#### 3. Health Check System (`app/status.py`, `app/llama_integration.py`)
- Configurable polling intervals
- Auth-isolated health monitoring
- Exponential backoff for failed checks

### Frontend Components

#### 1. Auth Orchestrator (`frontend/src/services/authOrchestrator.ts`)
- **Single source of truth** for authentication state
- **Centralized whoami calls** - only this component calls `/v1/whoami`
- **State management** with subscriber pattern
- **Bootstrap coordination** to prevent race conditions

#### 2. Auth Hooks (`frontend/src/hooks/useAuth.ts`)
- `useAuthState()` - Read-only access to auth state
- `useAuthOrchestrator()` - Access to auth actions
- **No direct whoami calls** from components

#### 3. WebSocket Hub (`frontend/src/services/wsHub.ts`)
- **Auth-aware connections** - only connect when authenticated
- **Limited reconnection** - maximum one reconnect attempt
- **Auth state coordination** - disconnect when auth is lost
- **Failure isolation** - WS failures don't affect auth state

#### 4. API Layer (`frontend/src/lib/api.ts`)
- **Auth namespace management** for cache invalidation
- **Request deduplication** to prevent duplicate calls
- **Cache control** with no-store headers for auth endpoints

#### 5. CSP Configuration (`frontend/src/lib/csp.ts`)
- **Strict Content Security Policy** in production
- **No-store headers** for authentication responses
- **Service worker prevention** for auth endpoints

## Testing Strategy

### Comprehensive Test Suite

The implementation includes a complete test suite that verifies every requirement:

#### Backend Tests (`tests/test_auth_behavior.py`)
- **Mock-based testing** with realistic scenarios
- **Network panel simulation** to track 401 responses
- **Auth orchestrator monitoring** to verify whoami call patterns
- **WebSocket behavior simulation** to test connection logic
- **Health check verification** to ensure auth isolation

#### Frontend Tests (`frontend/src/__tests__/authBehavior.test.tsx`)
- **React component testing** with React Testing Library
- **Hook behavior verification** for auth state management
- **Service mocking** to isolate authentication logic
- **Integration testing** for complete auth flows

### Test Runner (`scripts/test_auth_behavior.sh`)
- **Automated test execution** for both backend and frontend
- **Coverage reporting** to ensure comprehensive testing
- **CI/CD integration** ready
- **Multiple test modes** (backend, frontend, integration, coverage)

## Key Implementation Details

### 1. Single Whoami Call Enforcement

```typescript
// Only AuthOrchestrator can call whoami
class AuthOrchestratorImpl {
  async checkAuth(): Promise<void> {
    // Prevent duplicate calls
    if (this.state.isLoading) return;

    // Coordinate with bootstrap manager
    if (!this.bootstrapManager.startAuthBootstrap()) return;

    // Single whoami call
    const response = await apiFetch('/v1/whoami', { auth: false });
    // Update state and notify subscribers
  }
}
```

### 2. WebSocket Auth Coordination

```typescript
class WsHub {
  start(channels?: Record<WSName, boolean>) {
    // Only connect when authenticated
    if (!authState.isAuthenticated) return;

    // Connect to specified channels
    Object.entries(channels).forEach(([name, enabled]) => {
      if (enabled) this.connect(name);
    });
  }

  private connect(name: WSName) {
    // Limited reconnection attempts
    if (this.connections[name].reconnectAttempts >= 1) {
      this.surfaceConnectionFailure(name, "Max reconnection attempts reached");
      return;
    }
  }
}
```

### 3. Health Check Auth Isolation

```typescript
// Health checks never affect auth state
async function checkHealth() {
  const healthResult = await apiFetch('/health');
  // Update health state only
  // No auth state mutations
}
```

### 4. CSP and Cache Control

```typescript
// CSP configuration
export function getCSPPolicy(): string {
  return [
    "default-src 'self'",
    "connect-src 'self' https://api.gesahni.com",
    "script-src 'self' 'nonce-${nonce}'",
    // ... other directives
  ].join("; ");
}

// No-store headers for auth responses
response.headers.set('Cache-Control', 'no-store, no-cache');
```

## Verification and Validation

### Automated Testing

Run the complete test suite:

```bash
# Run all tests
./scripts/test_auth_behavior.sh

# Run specific test types
./scripts/test_auth_behavior.sh backend
./scripts/test_auth_behavior.sh frontend
./scripts/test_auth_behavior.sh integration
```

### Manual Verification

1. **Network Panel Check**: Open browser dev tools and verify no 401s during app boot
2. **Auth State Monitoring**: Use React DevTools to monitor auth state transitions
3. **WebSocket Behavior**: Test connection/disconnection scenarios
4. **Health Check Isolation**: Verify health polling doesn't affect auth state

### Performance Monitoring

- **Auth call frequency**: Monitor whoami call patterns
- **WebSocket reconnection**: Track connection failure rates
- **Health check overhead**: Monitor polling impact
- **Cache effectiveness**: Verify auth response caching prevention

## Security Considerations

### 1. Token Security
- JWT tokens with appropriate expiration
- Secure cookie configuration
- CSRF protection for mutating requests

### 2. State Management
- Centralized auth state to prevent inconsistencies
- No sensitive data in client-side storage
- Proper cleanup on logout

### 3. Network Security
- CSP headers to prevent XSS
- No-store headers for auth responses
- Secure WebSocket connections

### 4. Error Handling
- Graceful degradation on auth failures
- No sensitive information in error messages
- Proper logging for security events

## Maintenance and Evolution

### Adding New Features

When extending the authentication system:

1. **Update AuthOrchestrator** for new auth flows
2. **Add corresponding tests** to verify behavior
3. **Update documentation** to reflect changes
4. **Verify integration** with existing components

### Monitoring and Debugging

- **Auth state logging** for debugging
- **Performance metrics** for optimization
- **Error tracking** for issue resolution
- **User experience monitoring** for UX improvements

## Conclusion

The authentication behavior implementation provides a robust, secure, and predictable authentication system that meets all specified requirements. The comprehensive test suite ensures that the behavior remains consistent as the application evolves.

The implementation follows best practices for:
- **Security**: Proper token management, CSP, and error handling
- **Performance**: Efficient state management and network optimization
- **Maintainability**: Clear separation of concerns and comprehensive testing
- **User Experience**: Smooth authentication flows and graceful error handling

For more details, see:
- [Authentication Behavior Tests](docs/AUTHENTICATION_BEHAVIOR_TESTS.md)
- [Auth Orchestrator Implementation](frontend/src/services/authOrchestrator.ts)
- [WebSocket Hub Implementation](frontend/src/services/wsHub.ts)
- [API Authentication](app/deps/user.py)
