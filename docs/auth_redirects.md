# Authentication Redirect Security

This document describes the authentication redirect security implementation that prevents open redirects and redirect loops while maintaining proper post-login navigation flow.

## The Redirect Problem

### Problem Manifestation

The authentication system initially had inconsistent redirect behavior across different OAuth flows:

- **Legacy Google OAuth**: Set HttpOnly cookies directly on the `RedirectResponse` object before redirecting, ensuring cookies were included in the redirect response.
- **Modern Google OAuth**: Set cookies on one `Response` object but returned a separate `Response` for the 302 redirect, causing cookies to not be reliably included in the redirect.

This inconsistency led to unreliable post-login navigation where users might not be properly authenticated after OAuth completion.

### Security Risks

The original implementation exposed several security vulnerabilities:

1. **Open Redirects**: Absolute URLs in `?next=` parameters could redirect users to malicious external sites
2. **Redirect Loops**: Nested `?next=` parameters containing auth page URLs could create infinite redirect cycles
3. **Path Traversal**: URLs like `../../../etc/passwd` could potentially access sensitive paths
4. **Protocol-relative Redirects**: URLs starting with `//` could redirect to different protocols

## Sanitizer Contract

The redirect sanitizer enforces a strict set of rules to prevent security issues while allowing legitimate navigation:

### Core Rules

1. **Single-decode enforcement**: URLs are decoded at most twice to prevent nested encoding attacks
2. **Auth page prevention**: Redirects to authentication paths (`/login`, `/v1/auth/*`, `/google`, `/oauth`, `/sign-in`, `/sign-up`) are blocked
3. **Same-origin enforcement**: Only relative paths starting with `/` are allowed; absolute URLs are rejected
4. **Fragment stripping**: URL fragments (`#...`) are removed before validation
5. **Nested next removal**: Any `?next=` parameters embedded in the path are stripped
6. **Path normalization**: Multiple consecutive slashes are collapsed to single slashes
7. **Traversal protection**: Paths containing `..` are rejected

### Implementation Details

```python
def sanitize_redirect_path(raw_path: str | None) -> str:
    # 1. Safe URL decoding (at most twice)
    path = safe_decode_url(path, max_decodes=2)

    # 2. Reject absolute URLs
    if path.startswith(("http://", "https://")):
        return DEFAULT_FALLBACK

    # 3. Reject protocol-relative URLs
    if path.startswith("//") and not path.startswith("///"):
        return DEFAULT_FALLBACK

    # 4. Ensure path starts with /
    if not path.startswith("/"):
        return DEFAULT_FALLBACK

    # 5. Strip fragments
    if "#" in path:
        path = path.split("#")[0]

    # 6. Remove nested ?next= parameters
    # 7. Prevent auth path redirects
    # 8. Normalize slashes
    # 9. Reject path traversal
```

## Frontend Pattern

The frontend implements a secure redirect pattern using cookies for state management:

### Capture Next Once → Cookie → Clean URL

1. **Capture Phase**: When initiating authentication, the frontend captures the intended destination path
2. **Cookie Storage**: The `next` path is sent to the backend via a special login request that sets a `gs_next` cookie
3. **Clean URLs**: The authentication flow proceeds without `?next=` parameters in URLs

### Implementation

```typescript
// Capture next path to backend gs_next cookie
export async function captureNextPathToBackend(nextPath: string): Promise<void> {
    // POST to /v1/auth/login with special marker
    const response = await apiFetch('/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            username: '__capture_next__', // pragma: allowlist secret
            password: '__capture_next__', // pragma: allowlist secret
            next: nextPath,
        }),
    });
}

// Sanitize redirect paths client-side
export function sanitizeNextPath(rawPath: string | null | undefined): string {
    // Mirrors backend sanitization logic
    // Single decode, auth path blocking, etc.
}
```

### Cookie-Based Redirect Flow

1. User clicks "Login" with intended destination `/dashboard`
2. Frontend calls `captureNextPathToBackend('/dashboard')`
3. Backend sets `gs_next=/dashboard` cookie (5-minute TTL)
4. User completes OAuth/authentication
5. On success, backend reads `gs_next` cookie and redirects there
6. Cookie is cleared after use

## Test Coverage Overview

The redirect security implementation includes comprehensive test coverage:

### Unit Tests (`tests/unit/test_redirect_sanitizer.py`)

- **98 test cases** covering all sanitizer rules
- Parameterized tests for systematic validation
- Edge cases: double encoding, complex queries, Unicode handling
- Performance testing with long paths

### Security Tests (`tests/unit/test_security_redirects.py`)

- **Blocklisted path detection**: Exact and prefix matching
- **URL decoding safety**: Max decode limits
- **Sanitization rules**: All core security validations

### Integration Tests

- **E2E redirect flows**: Complete OAuth-to-redirect scenarios
- **Cookie handling**: gs_next cookie lifecycle
- **Cross-browser compatibility**: Cookie behavior validation

### Test Categories

| Test Type | File | Coverage |
|-----------|------|----------|
| Unit - Sanitizer | `test_redirect_sanitizer.py` | 98 cases, all rules |
| Unit - Security | `test_security_redirects.py` | Blocklisting, decoding |
| Integration | `test_auth_next_cookie.py` | Cookie-based redirects |
| E2E | `test_redirect_scenarios.py` | Full user flows |

### Security Validation

Tests ensure protection against:
- Open redirects to external domains
- Redirect loops via auth pages
- Path traversal attacks
- Protocol-relative URL exploits
- Nested parameter injection
- Double-encoding bypass attempts

## Migration Notes

When upgrading from URL-based `?next=` parameters:

1. **Remove `?next=` from login links**: No longer pass next destination in query parameters
2. **Use cookie capture**: Frontend must call `captureNextPathToBackend()` before authentication
3. **Backend compatibility**: Existing `?next=` parameters are still sanitized and supported as fallback
4. **Testing**: Verify that post-login redirects work correctly in all OAuth flows

The cookie-based approach provides better security, cleaner URLs, and more reliable cross-browser behavior.
