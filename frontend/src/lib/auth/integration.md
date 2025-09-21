# Authentication Mode Switching Integration Guide

## Overview

The authentication system now supports seamless switching between **cookie mode** and **header mode** with automatic fallback capabilities. This ensures your app works across all browsers and deployment scenarios.

## Quick Start

### 1. Initialize the Unified Orchestrator

```typescript
import { UnifiedAuthOrchestrator } from '@/lib/auth/orchestrator';
import { logSafariTestResults } from '@/lib/auth/safariTest';

// Initialize with automatic mode detection
const authOrchestrator = new UnifiedAuthOrchestrator(
  process.env.NEXT_PUBLIC_API_ORIGIN || 'http://localhost:8000'
);

// Initialize and auto-detect best mode
await authOrchestrator.initialize();

// Optional: Run Safari compatibility tests in development
if (process.env.NODE_ENV === 'development') {
  await logSafariTestResults(authOrchestrator.getApiUrl());
}
```

### 2. Use in React Components

```typescript
import { useAuthState } from '@/hooks/useAuth';

function MyComponent() {
  const { 
    isAuthenticated, 
    sessionReady, 
    user, 
    mode, 
    isLoading, 
    error 
  } = useAuthState();

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!isAuthenticated) return <LoginPrompt />;

  return (
    <div>
      <p>Welcome {user?.id}!</p>
      <p>Auth mode: {mode}</p>
    </div>
  );
}
```

## Mode Detection Priority

The system resolves authentication mode in this order:

1. **Explicit Override** - `?authMode=cookie|header` or `window.__AUTH_MODE_OVERRIDE`
2. **Server Preference** - `/v1/config` endpoint response
3. **Environment Variable** - `NEXT_PUBLIC_HEADER_AUTH_MODE=true`
4. **Auto-Detection** - Browser capability testing
5. **Last Known Good** - Stored in sessionStorage
6. **Default Fallback** - Cookie mode

## Environment Configuration

### Cookie Mode (Default)
```bash
# .env.local
NEXT_PUBLIC_HEADER_AUTH_MODE=false  # or omit entirely
NEXT_PUBLIC_API_ORIGIN=http://localhost:8000
```

### Header Mode
```bash
# .env.local
NEXT_PUBLIC_HEADER_AUTH_MODE=true
NEXT_PUBLIC_API_ORIGIN=http://localhost:8000
```

### Development Override
```javascript
// For testing - set in browser console or test setup
window.__AUTH_MODE_OVERRIDE = 'cookie'; // or 'header'
```

## Browser Compatibility

### ✅ Cookie Mode Works Well With:
- Modern Chrome, Firefox, Edge
- Safari 13+ with HTTPS
- iOS Safari with proper SameSite=Lax
- Same-origin deployments

### ⚠️ Cookie Mode Issues:
- Safari private browsing
- Cross-origin without proper CORS
- HTTP-only in production
- Third-party cookie blockers

### ✅ Header Mode Works Well With:
- All modern browsers
- Cross-origin deployments
- HTTP development environments
- When localStorage is available

### ⚠️ Header Mode Issues:
- Server-side rendering (no localStorage)
- Shared devices (tokens persist)
- XSS vulnerabilities if not careful

## Automatic Fallback Scenarios

The system automatically switches modes in these cases:

### Cookie → Header Fallback
```typescript
// Triggers when:
// 1. Safari blocks third-party cookies
// 2. Private browsing mode detected
// 3. CSRF/cookie errors in cookie mode
// 4. But header tokens exist in localStorage

if (cookieMode.fails() && localStorage.getItem('auth:access')) {
  await authOrchestrator.forceSwitchMode('header');
}
```

### Header → Cookie Fallback
```typescript
// Triggers when:
// 1. 401/498 errors in header mode
// 2. Server advertises cookie preference
// 3. localStorage unavailable

if (headerMode.fails() && server.prefersCookies()) {
  await authOrchestrator.forceSwitchMode('cookie');
}
```

## Manual Mode Switching

### Development/Testing
```typescript
// Force switch to specific mode
await authOrchestrator.forceSwitchMode('cookie');
await authOrchestrator.forceSwitchMode('header');

// Check current mode
const currentMode = authOrchestrator.getCurrentMode();
console.log('Current auth mode:', currentMode);
```

### Production Mode Selection
```typescript
import { setModeOverride } from '@/lib/auth/modeResolver';

// Set persistent override (until page reload)
setModeOverride('header');

// Clear override
setModeOverride(null);
```

## Error Handling

### Graceful Degradation
```typescript
const authState = authOrchestrator.getState();

if (authState.error) {
  // Show user-friendly error message
  if (authState.error.includes('network')) {
    showMessage('Check your internet connection');
  } else if (authState.error.includes('expired')) {
    showMessage('Please sign in again');
  } else {
    showMessage('Authentication service unavailable');
  }
}
```

### Safari-Specific Handling
```typescript
import { quickSafariCheck } from '@/lib/auth/safariTest';

const safariCompatible = await quickSafariCheck(apiUrl);
if (!safariCompatible) {
  // Recommend header mode for problematic Safari setups
  await authOrchestrator.forceSwitchMode('header');
}
```

## Testing

### Unit Tests
```typescript
import { setModeOverride } from '@/lib/auth/modeResolver';

describe('Auth Mode Switching', () => {
  it('should use cookie mode by default', async () => {
    const auth = new UnifiedAuthOrchestrator(API_URL);
    await auth.initialize();
    expect(auth.getCurrentMode()).toBe('cookie');
  });

  it('should switch to header mode when forced', async () => {
    setModeOverride('header');
    const auth = new UnifiedAuthOrchestrator(API_URL);
    await auth.initialize();
    expect(auth.getCurrentMode()).toBe('header');
  });
});
```

### E2E Tests (Playwright)
```typescript
test('cookie mode authentication flow', async ({ page }) => {
  await page.addInitScript(() => {
    window.__AUTH_MODE_OVERRIDE = 'cookie';
  });
  
  await page.goto('/login');
  // ... test login flow
  
  // Verify cookies are set
  const cookies = await page.context().cookies();
  expect(cookies.find(c => c.name === 'GSNH_AT')).toBeTruthy();
});
```

## Migration from Legacy System

### Step 1: Update Environment Variables
```bash
# Old
NEXT_PUBLIC_USE_HEADER_AUTH=true

# New
NEXT_PUBLIC_HEADER_AUTH_MODE=true
```

### Step 2: Replace Auth Calls
```typescript
// Old
import { getToken, isAuthed } from '@/lib/api/auth';

if (isAuthed()) {
  const token = getToken();
  // ...
}

// New
import { useAuthState } from '@/hooks/useAuth';

const { isAuthenticated, mode } = useAuthState();
if (isAuthenticated) {
  // Mode is automatically handled
  // ...
}
```

### Step 3: Update API Calls
```typescript
// Old
const response = await fetch('/api/data', {
  headers: {
    Authorization: `Bearer ${getToken()}`
  }
});

// New - automatic mode handling
const response = await apiFetch('/api/data');
```

## Production Deployment

### Same-Origin Setup (Recommended for Cookie Mode)
```nginx
# nginx config
server {
  listen 443 ssl;
  server_name myapp.com;
  
  location /api/ {
    proxy_pass http://backend:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
  }
  
  location / {
    proxy_pass http://frontend:3000/;
  }
}
```

### Cross-Origin Setup (Use Header Mode)
```bash
# Backend CORS config
CORS_ALLOW_ORIGINS=https://myapp.com,https://app.myapp.com
CORS_ALLOW_CREDENTIALS=true

# Frontend config
NEXT_PUBLIC_HEADER_AUTH_MODE=true
NEXT_PUBLIC_API_ORIGIN=https://api.myapp.com
```

## Troubleshooting

### Common Issues

1. **Safari Private Mode Blocks Cookies**
   - Solution: Automatic fallback to header mode
   - Detection: `browserDetails.isPrivate === true`

2. **Cross-Origin Cookie Issues**
   - Solution: Ensure HTTPS + proper SameSite
   - Alternative: Use header mode

3. **localStorage Unavailable**
   - Solution: Automatic fallback to cookie mode
   - Common in: SSR, some mobile browsers

4. **Mode Oscillation**
   - Symptom: Rapid switching between modes
   - Solution: Check for conflicting configurations

### Debug Information
```typescript
// Check current auth state
console.log('Auth State:', authOrchestrator.getState());

// Check mode resolution
import { resolveAuthMode } from '@/lib/auth/modeResolver';
const resolution = await resolveAuthMode(apiUrl);
console.log('Mode Resolution:', resolution);

// Check Safari compatibility
import { logSafariTestResults } from '@/lib/auth/safariTest';
await logSafariTestResults(apiUrl);
```

## Security Considerations

### Cookie Mode Security
- ✅ HTTP-only cookies prevent XSS
- ✅ SameSite=Lax prevents CSRF
- ✅ Secure flag for HTTPS
- ⚠️ Vulnerable to CSRF without proper tokens

### Header Mode Security
- ✅ Explicit token management
- ✅ Works with CORS
- ⚠️ Vulnerable to XSS if tokens leaked
- ⚠️ Tokens persist in localStorage

### Best Practices
1. Use HTTPS in production
2. Implement proper CSRF protection
3. Set appropriate cookie expiry times
4. Monitor for auth failures and fallbacks
5. Test across different browsers and modes
