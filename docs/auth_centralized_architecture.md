# Centralized Authentication Architecture

## Overview

The authentication system has been centralized with a single "Auth Orchestrator" that manages all authentication state and is the only component allowed to call `/v1/whoami` directly. This eliminates race conditions, reduces redundant API calls, and provides a single source of truth for authentication state.

## Architecture Components

### 1. Auth Orchestrator (`frontend/src/services/authOrchestrator.ts`)

**Purpose**: Centralized authentication authority that owns the authentication state and manages all whoami calls.

**Key Features**:
- **Single Source of Truth**: Only component allowed to call `/v1/whoami`
- **State Management**: Maintains authentication state with subscribers
- **Race Condition Prevention**: Blocks whoami calls during auth finish
- **Idempotent**: Safe to call multiple times
- **Event-Driven**: Listens for auth finish events

**Core Methods**:
- `initialize()`: Called on app mount, performs initial auth check
- `checkAuth()`: Calls `/v1/whoami` and updates state
- `refreshAuth()`: Refreshes authentication state
- `getState()`: Returns current auth state
- `subscribe(callback)`: Subscribe to auth state changes

### 2. Auth Provider (`frontend/src/components/AuthProvider.tsx`)

**Purpose**: React component that initializes the Auth Orchestrator on app mount.

**Responsibilities**:
- Initializes Auth Orchestrator when app loads
- Provides cleanup on unmount
- Wraps the entire app to ensure auth state is available

### 3. Auth Hooks (`frontend/src/hooks/useAuth.ts`)

**Purpose**: React hooks for components to access authentication state.

**Available Hooks**:
- `useAuthState()`: Returns current authentication state
- `useAuthOrchestrator()`: Returns the orchestrator instance
- `useAuth()`: Returns both state and orchestrator

## Authentication State Interface

```typescript
interface AuthState {
  isAuthenticated: boolean;      // Whether user is authenticated
  sessionReady: boolean;         // Whether session is ready for use
  user: {                        // User information
    id: string | null;
    email: string | null;
  } | null;
  source: 'cookie' | 'header' | 'clerk' | 'missing';  // Auth source
  version: number;               // API version
  lastChecked: number;           // Timestamp of last check
  isLoading: boolean;            // Whether auth check is in progress
  error: string | null;          // Error message if any
}
```

## Usage Patterns

### For Components That Need Auth State

```typescript
import { useAuthState } from '@/hooks/useAuth';

function MyComponent() {
  const authState = useAuthState();

  if (authState.isLoading) {
    return <div>Loading...</div>;
  }

  if (!authState.isAuthenticated) {
    return <div>Please log in</div>;
  }

  return <div>Welcome, {authState.user?.id}!</div>;
}
```

### For Components That Need to Trigger Auth Actions

```typescript
import { useAuthOrchestrator } from '@/hooks/useAuth';

function LogoutButton() {
  const orchestrator = useAuthOrchestrator();

  const handleLogout = async () => {
    // Perform logout
    await apiFetch('/v1/auth/logout', { method: 'POST' });
    // Refresh auth state
    await orchestrator.refreshAuth();
  };

  return <button onClick={handleLogout}>Logout</button>;
}
```

## Migration from Direct Whoami Calls

### Before (Banned Pattern)
```typescript
// ❌ DON'T DO THIS - Direct whoami call
const response = await apiFetch('/v1/whoami');
const isAuthed = response.ok && (await response.json()).is_authenticated;
```

### After (Centralized Pattern)
```typescript
// ✅ DO THIS - Use centralized auth state
import { useAuthState } from '@/hooks/useAuth';

function MyComponent() {
  const authState = useAuthState();
  const isAuthed = authState.isAuthenticated;
  // ...
}
```

## Event System

The Auth Orchestrator listens for and emits events to coordinate authentication flows:

### Events Listened To
- `auth:finish_start`: Auth finish process started (blocks whoami calls)
- `auth:finish_end`: Auth finish process ended (allows whoami calls, triggers refresh)

### Events Emitted
- State changes are broadcast to all subscribers automatically

## Development Helper

In development mode, the Auth Orchestrator includes a helper that detects direct whoami calls and warns developers:

```javascript
// Development warning for direct whoami calls
🚨 DIRECT WHOAMI CALL DETECTED! {
  url: "/v1/whoami",
  stack: "Error stack trace",
  message: "Use AuthOrchestrator instead of calling whoami directly"
}
```

## Benefits

### 1. Eliminates Race Conditions
- Single whoami call on mount
- Blocked during auth finish
- Coordinated state updates

### 2. Reduces API Calls
- No redundant whoami calls from multiple components
- Deduplication of simultaneous requests
- Efficient state sharing

### 3. Consistent State
- Single source of truth for authentication
- All components see the same auth state
- Predictable behavior

### 4. Better Performance
- Fewer network requests
- Faster component rendering
- Reduced server load

### 5. Easier Debugging
- Centralized logging
- Clear auth flow
- Development warnings

## Migration Checklist

### Components Updated
- [x] `Header.tsx` - Uses centralized auth state
- [x] `page.tsx` - Uses centralized auth state
- [x] `wsHub.ts` - Uses centralized auth state
- [x] `login/page.tsx` - Triggers auth refresh after login
- [x] `layout.tsx` - Includes AuthProvider

### Components That Should Be Updated
- [ ] Any component making direct whoami calls
- [ ] Components using local auth state
- [ ] Components with auth-related useEffect hooks

### Testing
- [ ] Verify auth state is consistent across components
- [ ] Test auth finish flow
- [ ] Test logout flow
- [ ] Test error handling
- [ ] Verify no direct whoami calls in development

## Future Enhancements

### 1. Persistence
- Cache auth state in localStorage
- Restore state on page reload

### 2. Automatic Refresh
- Refresh tokens before expiry
- Background auth checks

### 3. Offline Support
- Handle offline scenarios
- Queue auth actions

### 4. Metrics
- Track auth state changes
- Monitor whoami call frequency

## Conclusion

The centralized authentication architecture provides a robust, efficient, and maintainable solution for managing authentication state across the application. By centralizing authority in the Auth Orchestrator, we eliminate race conditions, reduce redundant API calls, and provide a single source of truth for authentication state.
