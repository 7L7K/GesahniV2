# SQL Doctor

A diagnostic and repair tool for SQLite schema conflicts in GesahniV2.

## Problem

GesahniV2 has multiple conflicting SQLite database schemas, particularly around the `users` table:

- **Canonical schema** (`app/auth_store.py`): Email-based authentication with columns like `id`, `email`, `password_hash`, `name`, etc.
- **Legacy conflicts**: Some code expects username-based authentication with `username`, `password_hash` columns
- **Migration issues**: Code attempts `INSERT ... SELECT username FROM users` but the canonical schema doesn't have a `username` column

## What SQL Doctor Does

1. **Discovers** all SQLite databases in the project
2. **Diagnoses** schema conflicts and incompatibilities
3. **Resets** databases with canonical schemas (WARNING: destroys data)

## Usage

### Diagnosis Mode

```bash
python scripts/sql_doctor.py --diagnose
```

Analyzes all SQLite databases and reports:
- Database file sizes and paths
- Table schemas, especially `users` and `auth_users` tables
- Conflict detection with specific error messages
- Exit code 2 if conflicts found, 0 if clean

### Reset Mode

```bash
python scripts/sql_doctor.py --reset --yes
```

**WARNING: This deletes all SQLite databases and recreates them with canonical schemas!**

- Requires `--yes` flag for confirmation
- Deletes: `auth.db`, `users.db`, `third_party_tokens.db`, `music.db`, `music_tokens.db`, `care.db`, `notes.db`
- Recreates all tables with canonical schemas
- Safe for development (data loss acceptable)

## Detected Conflicts

Current issues in GesahniV2:

1. **users.db conflict**: `auth_users` table expects `username` column from `users` table, but `users` table uses email-based schema
2. **Mixed schemas**: Some databases have canonical email-based `users` tables, others have legacy username-based tables

## Canonical Schema

The tool recreates these tables with the canonical schema:

### Authentication Tables (auth.db)
- `users` - Email-based user accounts
- `devices` - User device tracking
- `sessions` - User sessions
- `auth_identities` - OAuth identities
- `pat_tokens` - Personal access tokens
- `audit_log` - Security audit log

### Care Tables (care.db)
- `residents` - Care recipients
- `caregivers` - Care providers
- `caregiver_resident` - Relationships
- `care_sessions` - Care activities
- `contacts` - Emergency contacts
- `tv_config` - TV preferences

### Music Tables (music.db, music_tokens.db)
- `music_tokens` - Streaming service tokens
- `music_devices` - Playback devices
- `music_preferences` - User preferences
- `music_sessions` - Playback sessions
- `music_queue` - Song queues
- `music_feedback` - User feedback
- `music_idempotency` - Duplicate prevention

### Other Tables
- `notes` - User notes
- `alerts` / `alert_events` - Care alerts
- `user_stats` - Usage statistics

## Development Workflow

1. Run diagnosis: `python scripts/sql_doctor.py --diagnose`
2. If conflicts found, review the report
3. Reset if needed: `python scripts/sql_doctor.py --reset --yes`
4. Restart GesahniV2 services

## Exit Codes

- `0`: No conflicts detected
- `1`: Command error (missing flags, etc.)
- `2`: Schema conflicts detected

## Safety

- Diagnosis mode is read-only and safe
- Reset mode requires explicit `--yes` confirmation
- Always backup important data before running reset
- Designed for development environments where data loss is acceptable
