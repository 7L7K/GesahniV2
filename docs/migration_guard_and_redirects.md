# Migration Guard: Cookie-Based Redirects

## Overview

This document describes the migration from URL-based redirects (`/login?next=`) to cookie-based redirects using the `gs_next` cookie pattern. A migration guard prevents reintroduction of forbidden URL patterns in CI.

## 🎯 **Migration Goal**

Replace all `/login?next=` patterns with cookie-based redirect capture for improved security and consistency.

## 🔒 **Canonical Cookie Capture Pattern**

### Frontend Implementation
```typescript
// Set redirect cookie before navigation to login
const setRedirectCookie = async (path: string) => {
  const response = await fetch('/api/auth/set-redirect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
    credentials: 'include' // Include cookies
  });
  return response.ok;
};

// Usage in protected routes
if (!authState.isAuthenticated) {
  await setRedirectCookie('/dashboard');
  router.push('/login');
}
```

### Backend Implementation
```python
from app.redirect_utils import set_gs_next_cookie, sanitize_redirect_path
from fastapi import Request, Response

@app.post('/api/auth/set-redirect')
async def set_redirect_cookie(request: Request, path: str):
    """
    Set gs_next cookie for post-login redirect.

    Validates and sanitizes the redirect path before storing in cookie.
    """
    safe_path = sanitize_redirect_path(path, fallback='/dashboard', request=request)

    if safe_path and safe_path != '/dashboard':  # Only set if different from fallback
        response = Response(content='{"status": "ok"}', media_type='application/json')
        set_gs_next_cookie(response, safe_path, request)
        return response

    return {"status": "ok"}  # No cookie needed for default fallback
```

### Post-Login Redirect Handling
```python
from app.redirect_utils import get_safe_redirect_target

@app.get('/v1/auth/login')
async def login_page(request: Request):
    """
    Login page that handles post-login redirects.
    """
    if request.user.is_authenticated:
        # Get safe redirect target (priority: explicit next -> cookie -> fallback)
        redirect_to = get_safe_redirect_target(request, fallback='/dashboard')
        return RedirectResponse(redirect_to, status_code=302)

    return templates.TemplateResponse("login.html", {"request": request})
```

## 🚫 **Forbidden Patterns (CI Blocked)**

The following patterns are forbidden and will cause CI to fail:

```typescript
// ❌ DON'T USE - These patterns are blocked by migration guard
router.push(`/login?next=${encodeURIComponent('/dashboard')}`);
router.replace('/login?next=%2Fdashboard');
window.location.href = '/login?next=/settings';

// ❌ Backend patterns (also forbidden)
redirect_url = f"/login?next={user_path}"
return RedirectResponse(f"/login?next={safe_path}")
```

## 🔧 **Migration Guard CI Integration**

### Running the Guard
```bash
# Check for forbidden patterns
make migration-guard

# Run as part of docs-and-links check
make docs-and-links

# Manual execution
./tools/grep_guard.sh --verbose
./tools/grep_guard.sh --fix  # Show suggestions
```

### CI Integration
The migration guard is integrated into the CI pipeline:

```yaml
# Example CI configuration
jobs:
  docs-and-links:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Migration Guard
        run: make migration-guard
      - name: Additional docs checks
        run: # ... other checks
```

### Guard Script Features
- **Multi-pattern detection**: Detects various forms of `/login?next=` patterns
- **Exclude patterns**: Ignores build artifacts, caches, and generated files
- **Verbose output**: Shows detailed matches with file locations
- **Fix suggestions**: Provides guidance on replacing forbidden patterns
- **Fast execution**: Uses `grep -r` for efficient searching

## 📊 **Migration Status**

### ✅ **Current State**
- Migration guard implemented and active
- Cookie capture pattern documented as canonical
- CI integration complete
- Multiple test cases validate cookie-based redirects

### 🔄 **In Progress**
- Gradual replacement of existing `/login?next=` patterns in tests and docs
- Frontend component updates to use cookie capture
- Documentation updates to reflect canonical pattern

### 📋 **Remaining Work**
- Update e2e tests to use cookie capture pattern
- Audit and update documentation examples
- Consider automated migration tooling for bulk replacements

## 🧪 **Testing the Migration Guard**

### Example Failing Output
```bash
$ make migration-guard
== Migration Guard: Checking for forbidden /login?next= patterns ==
⚠️  Found 3 matches of '/login?next=' in 2 files
⚠️  Found 1 matches of '/login\?next=' in 1 files

🚫 MIGRATION GUARD FAILURE
Found 4 violations of forbidden patterns in 2 pattern types

Forbidden patterns detected:
  ❌ /login?next=
  ❌ /login\?next=

Affected files:
  📁 docs/example.md
  📁 frontend/src/components/LoginButton.tsx

💡 FIX SUGGESTIONS for pattern '/login?next=':
Replace URL-based redirects with cookie-based pattern:

❌ AVOID:
   /login?next=/dashboard
   router.push('/login?next=' + encodeURIComponent(path))

✅ USE:
   // Set cookie for post-login redirect
   set_gs_next_cookie(response, path, request)
   // Then redirect to login
   return RedirectResponse('/login', status_code=302)

   // Or in frontend:
   await setRedirectCookie(path)
   router.push('/login')

📁 Files containing this pattern:
   - docs/example.md
   - frontend/src/components/LoginButton.tsx

💡 RECOMMENDATION:
Replace /login?next= patterns with gs_next cookie-based redirects.
See: app/redirect_utils.py for canonical implementation.

🚫 CI FAILURE: Migration guard detected forbidden patterns
make: *** [migration-guard] Error 1
```

### Example Success Output
```bash
$ make migration-guard
== Migration Guard: Checking for forbidden /login?next= patterns ==
✅ MIGRATION GUARD SUCCESS
No forbidden /login?next= patterns found

🎉 All redirect patterns use cookie-based approach!
```

## 🔗 **Related Documentation**

- [`app/redirect_utils.py`](../app/redirect_utils.py) - Core redirect utilities
- [`docs/auth_gating_implementation_summary.md`](auth_gating_implementation_summary.md) - Authentication patterns
- [`tools/grep_guard.sh`](../tools/grep_guard.sh) - Migration guard implementation
- [`Makefile`](../Makefile) - CI integration

## 📞 **Support**

For questions about redirect patterns or migration guard issues:
1. Check existing implementations in `app/redirect_utils.py`
2. Review test cases in `tests/unit/test_redirect_*`
3. Run `./tools/grep_guard.sh --fix` for suggestions
4. See [CONTRIBUTING.md](../CONTRIBUTING.md) for contribution guidelines
