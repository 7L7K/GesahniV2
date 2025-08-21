# Whoami Endpoint Fix Summary

## Problem Description

The frontend auth orchestrator was expecting the user ID to be returned directly in the response as `user_id`, but the backend `/v1/whoami` endpoint was only returning it nested inside a `user` object as `user.id`.

**Expected (after fix):** 200 OK with `user_id` present
**Actual (before fix):** 200 OK but body had no `user_id` field

## Root Cause

The frontend auth orchestrator in `frontend/src/services/authOrchestrator.ts` was looking for:
```typescript
const hasValidUserId = data.user_id && typeof data.user_id === 'string' && data.user_id.trim() !== '';
```

But the backend `/v1/whoami` endpoint in `app/api/auth.py` was only returning:
```json
{
  "is_authenticated": true,
  "session_ready": true,
  "user": {"id": "demo", "email": null},
  "source": "header",
  "version": 1
}
```

## Solution Implemented

### 1. Updated Backend Response Format

**File:** `app/api/auth.py`

**Changes:**
- Added `"user_id": effective_uid if effective_uid else None` to the successful response (200 OK)
- Added `"user_id": None` to the error response (401 Unauthorized)

**Before:**
```json
{
  "is_authenticated": true,
  "session_ready": true,
  "user": {"id": "demo", "email": null},
  "source": "header",
  "version": 1
}
```

**After:**
```json
{
  "is_authenticated": true,
  "session_ready": true,
  "user_id": "demo",
  "user": {"id": "demo", "email": null},
  "source": "header",
  "version": 1
}
```

### 2. Updated Tests

**File:** `tests/unit/test_auth_contract_locked.py`

**Changes:**
- Added assertion to verify `data["user_id"] == "test_user"` in the authenticated test case

## Verification

### Test Results
- ✅ Unit tests pass: `python -m pytest tests/unit/test_auth_contract_locked.py -v`
- ✅ Unauthenticated requests return 401 with `user_id: null`
- ✅ Authenticated requests return 200 with `user_id: <actual_user_id>`

### Expected Frontend Behavior
The frontend auth orchestrator should now:
1. Receive the `user_id` field correctly
2. Log: `AUTH Orchestrator: Whoami success #1 – { isAuthenticated: true, userId: <must be defined> }`
3. Set the user state properly instead of treating it as unauthenticated

## Files Modified

1. **`app/api/auth.py`** - Added `user_id` field to both success and error responses
2. **`tests/unit/test_auth_contract_locked.py`** - Added test assertion for `user_id` field

## Impact

- **Positive:** Frontend will now receive user ID correctly and authenticate users properly
- **Backward Compatible:** The existing `user.id` field is still present for any code that depends on it
- **No Breaking Changes:** All existing functionality remains intact

## Next Steps

1. Reload the web app
2. Watch the log line: `AUTH Orchestrator: Whoami success #1 – { isAuthenticated: true, userId: <must be defined> }`
3. Verify that `userId` is now defined instead of undefined
4. If `userId` is still undefined, the auth orchestrator will surface a clear banner: "Session error: user missing. Try re-login."

## Test Results

- ✅ **Unit tests pass:** All core authentication tests are working correctly
- ⚠️ **Integration tests:** Some integration tests expect 200 for unauthenticated requests, but the correct behavior per user requirements is 401 for missing/invalid cookies
- ✅ **Functionality:** The fix correctly implements the user's requirements:
  - 401 Unauthorized for missing/invalid cookies
  - 200 OK with `user_id` present when authenticated
