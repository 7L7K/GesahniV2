# Legacy ID Leaking Fix Summary

## Problem Identified

The application was experiencing database errors due to legacy usernames (9-character handles like `qazwsxppo`) being passed directly to database queries that expect UUIDs. This caused errors like:

```
invalid input for query argument $1: 'qazwsxppo' (invalid UUID 'qazwsxppo': length must be between 32..36 characters, got 9)
```

## Root Cause

The issue was in multiple database query methods where `user_id` parameters were being used directly in SQLAlchemy queries without converting them to UUIDs first. The database schema expects UUIDs, but the application was receiving legacy usernames from JWT tokens.

## Files Fixed

### 1. `app/sessions_store.py`
- **Fixed methods:**
  - `create_session()` - Convert user_id to UUID before creating AuthDevice and SessionModel
  - `list_user_sessions()` - Convert user_id to UUID before querying sessions
  - `rename_device()` - Convert user_id to UUID before verifying device ownership
  - `revoke_device_sessions()` - Convert user_id to UUID before revoking sessions
  - `revoke_all_user_sessions()` - Convert user_id to UUID before revoking all sessions

### 2. `app/auth_store.py`
- **Fixed methods:**
  - `list_pats_for_user()` - Convert user_id to UUID before querying PAT tokens

### 3. `app/auth_store_tokens.py`
- **Fixed methods:**
  - `update_service_state()` - Convert user_id to UUID before querying third-party tokens

### 4. `app/cron/google_refresh.py`
- **Fixed methods:**
  - `refresh_google_token()` - Convert user_id to UUID before querying tokens

### 5. `app/cron/spotify_refresh.py`
- **Fixed methods:**
  - `refresh_spotify_token()` - Convert user_id to UUID before querying tokens

### 6. `app/api/admin.py`
- **Fixed methods:**
  - `list_user_identities()` - Convert user_id to UUID before querying identities
  - `unlink_identity()` - Convert user_id to UUID before verifying identity ownership

## Solution Applied

All fixed methods now use the `to_uuid()` utility function to convert legacy usernames to deterministic UUIDs:

```python
from app.util.ids import to_uuid
db_user_id = str(to_uuid(user_id))
```

The `to_uuid()` function:
- Returns the input unchanged if it's already a valid UUID
- Generates a deterministic UUID using `uuid.uuid5()` with a fixed namespace for legacy usernames
- Ensures consistent UUID generation for the same input

## Database Schema Status

- **Third-party tokens table**: ✅ Correctly uses BYTEA for encrypted token columns
- **Sessions table**: ✅ No legacy IDs found in database
- **All other tables**: ✅ No legacy IDs found in database

## Migration Created

Created `app/migrations/005_fix_legacy_user_ids.sql` as a diagnostic tool to check for any existing legacy IDs in the database. The diagnostic shows all tables are clean (0 legacy IDs found).

## Testing

- ✅ UUID conversion function works correctly
- ✅ No linter errors introduced
- ✅ Database diagnostic shows no existing legacy IDs
- ✅ All database queries now use proper UUIDs

## Impact

This fix resolves the `psycopg2.errors.InvalidTextRepresentation` errors that were occurring when legacy usernames were passed to database queries. The application now properly handles both legacy usernames and proper UUIDs by converting them to consistent UUIDs before database operations.

## Files Already Using Correct Pattern

The following files were already correctly using `to_uuid()` conversion:
- `app/music/store.py`
- `app/db/chat_repo.py`
- `app/storage.py`
- `app/user_store.py`
- `app/auth_store_tokens.py` (most methods)

## Prevention

All new database query methods should follow this pattern:
1. Import `from app.util.ids import to_uuid`
2. Convert user_id: `db_user_id = str(to_uuid(user_id))`
3. Use `db_user_id` in database queries

This ensures consistent UUID handling regardless of whether the input is a legacy username or a proper UUID.
